#!/usr/bin/env bash
# VISHWAAS Setup — run once on the target machine.
# Installs Python 3.11 to /opt/vishwaas/python, creates venv, installs all packages offline.
#
# Usage:
#   sudo ./setup.sh controller
#   sudo ./setup.sh agent
set -e

PACK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="${1:-}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[✗]${NC} $*"; exit 1; }
step()  { echo -e "\n${YELLOW}━━ $* ━━${NC}"; }

[[ $EUID -ne 0 ]] && error "Run as root: sudo ./setup.sh $MODE"

if [[ "$MODE" != "controller" && "$MODE" != "agent" ]]; then
    echo "Usage: sudo ./setup.sh <controller|agent>"
    echo ""
    echo "  controller  — set up on the admin/dashboard machine"
    echo "  agent       — set up on each VPN node machine"
    exit 1
fi

# ── 1. Install Python 3.11 ────────────────────────────────────────────────────
step "Installing Python 3.11"

PYTHON_DIR="/opt/vishwaas/python"

mkdir -p "$PYTHON_DIR"
# Always overwrite — ensures clean known version
cp -a "$PACK_DIR/python/." "$PYTHON_DIR/"
PYTHON="$PYTHON_DIR/bin/python3.11"

[[ -x "$PYTHON" ]] || error "Python binary not found after install. Pack may be corrupted."
info "Python $($PYTHON --version) installed at $PYTHON_DIR"

# ── 2. Install system packages (nginx / wireguard) ────────────────────────────
step "Installing system packages"

if [[ "$MODE" == "controller" ]]; then
    for rpm in "$PACK_DIR/repo"/nginx*.rpm "$PACK_DIR/repo"/oracle-logos*.rpm; do
        [[ -f "$rpm" ]] && dnf install -y --nogpgcheck "$rpm" 2>/dev/null || true
    done
    systemctl enable --now nginx 2>/dev/null && info "nginx installed and started" || warn "nginx start skipped"
else
    RPM=$(find "$PACK_DIR/repo" -name "wireguard-tools*.rpm" | head -1)
    if [[ -n "$RPM" ]]; then
        dnf install -y --nogpgcheck "$RPM" && info "wireguard-tools installed" || warn "wireguard-tools install failed"
    fi
    modprobe wireguard 2>/dev/null && info "WireGuard kernel module loaded" || \
        warn "Could not load wireguard module — may need kernel-modules-extra"
fi

# ── 3. Copy code to /opt/vishwaas ─────────────────────────────────────────────
step "Installing VISHWAAS $MODE to /opt/vishwaas/$MODE"

if [[ "$MODE" == "controller" ]]; then
    INSTALL_DIR="/opt/vishwaas/controller"
    mkdir -p "$INSTALL_DIR/logs"

    rsync -a --delete \
        --exclude='__pycache__' --exclude='*.pyc' --exclude='.venv' \
        --exclude='*.db' --exclude='.env' \
        "$PACK_DIR/controller/backend/" "$INSTALL_DIR/backend/"

    rsync -a --delete \
        "$PACK_DIR/controller/frontend/dist/" "$INSTALL_DIR/frontend/dist/"

    cp "$PACK_DIR/controller/start_controller.sh" "$INSTALL_DIR/"
    cp "$PACK_DIR/controller/nginx.conf"          "$INSTALL_DIR/"
    chmod +x "$INSTALL_DIR/start_controller.sh"

else
    INSTALL_DIR="/opt/vishwaas/agent"
    mkdir -p "$INSTALL_DIR"

    rsync -a --delete \
        --exclude='__pycache__' --exclude='*.pyc' --exclude='venv' \
        --exclude='keys' --exclude='agent_config.json' \
        "$PACK_DIR/agent/" "$INSTALL_DIR/"

    chmod +x "$INSTALL_DIR/start_agent.sh"
fi

info "Code installed to $INSTALL_DIR"

# ── 4. Create venv and install Python packages ────────────────────────────────
step "Creating Python virtual environment and installing packages"

if [[ "$MODE" == "controller" ]]; then
    VENV="$INSTALL_DIR/backend/.venv"
    WHEELS="$PACK_DIR/controller/pip_packages"
    REQS="$INSTALL_DIR/backend/requirements.txt"
else
    VENV="$INSTALL_DIR/venv"
    WHEELS="$PACK_DIR/agent/pip_packages"
    REQS="$INSTALL_DIR/requirements.txt"
fi

"$PYTHON" -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip --no-index --find-links="$WHEELS"
"$VENV/bin/pip" install --quiet --no-index --find-links="$WHEELS" -r "$REQS"

# Verify uvicorn is installed
"$VENV/bin/python" -c "import uvicorn" || error "uvicorn not installed — pip install may have failed"
info "All Python packages installed (offline)"

# ── 5. Controller: generate .env + configure nginx ───────────────────────────
if [[ "$MODE" == "controller" ]]; then
    step "Configuring controller"

    if [[ ! -f "$INSTALL_DIR/backend/.env" ]]; then
        cp "$INSTALL_DIR/backend/.env.example" "$INSTALL_DIR/backend/.env"
        AGENT_TOKEN=$(openssl rand -hex 32)
        JWT_SECRET=$(openssl rand -hex 32)
        sed -i "s|your-secret-token-here|$AGENT_TOKEN|" "$INSTALL_DIR/backend/.env"
        sed -i "s|change-me-in-production|$JWT_SECRET|"  "$INSTALL_DIR/backend/.env"
    else
        AGENT_TOKEN=$(grep VISHWAAS_AGENT_TOKEN "$INSTALL_DIR/backend/.env" | cut -d= -f2)
        info ".env already exists — keeping"
    fi

    # nginx config
    cat > /etc/nginx/conf.d/vishwaas.conf <<NGINXEOF
server {
    listen 80;
    server_name _;
    root $INSTALL_DIR/frontend/dist;
    index index.html;
    location / { try_files \$uri \$uri/ /index.html; }
    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_read_timeout 60s;
    }
}
NGINXEOF
    nginx -t && systemctl reload nginx && info "nginx configured"

    # Firewall
    if systemctl is-active firewalld &>/dev/null; then
        firewall-cmd --permanent --add-service=http --add-port=8000/tcp &>/dev/null
        firewall-cmd --reload &>/dev/null
        info "Firewall: ports 80, 8000 opened"
    fi
fi

# ── 6. Agent: create config + firewall ───────────────────────────────────────
if [[ "$MODE" == "agent" ]]; then
    step "Configuring agent"

    mkdir -p /etc/vishwaas/keys && chmod 700 /etc/vishwaas/keys

    if [[ ! -f "$INSTALL_DIR/agent_config.json" ]]; then
        cp "$INSTALL_DIR/agent_config.json.example" "$INSTALL_DIR/agent_config.json"
        THIS_IP=$(hostname -I | awk '{print $1}')
        sed -i "s|http://THIS_MACHINE_IP:9000|http://$THIS_IP:9000|" "$INSTALL_DIR/agent_config.json"
    else
        info "agent_config.json already exists — keeping"
    fi

    if systemctl is-active firewalld &>/dev/null; then
        firewall-cmd --permanent --add-port=9000/tcp --add-port=51820/udp &>/dev/null
        firewall-cmd --reload &>/dev/null
        info "Firewall: ports 9000, 51820 opened"
    fi
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Setup complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

if [[ "$MODE" == "controller" ]]; then
    CONTROLLER_IP=$(hostname -I | awk '{print $1}')
    echo "  VISHWAAS_AGENT_TOKEN = $AGENT_TOKEN"
    echo "  (copy this into each agent's agent_config.json as master_token)"
    echo ""
    echo "  ── Start the controller ──────────────────────────────"
    echo "  cd $INSTALL_DIR && ./start_controller.sh"
    echo ""
    echo "  Dashboard: http://$CONTROLLER_IP/"
fi

if [[ "$MODE" == "agent" ]]; then
    echo "  ── Edit config then start ────────────────────────────"
    echo "  nano $INSTALL_DIR/agent_config.json"
    echo "    master_url   = http://<controller-ip>:8000"
    echo "    master_token = <VISHWAAS_AGENT_TOKEN from controller>"
    echo ""
    echo "  cd $INSTALL_DIR && sudo ./start_agent.sh"
fi
echo ""
