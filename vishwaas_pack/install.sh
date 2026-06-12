#!/usr/bin/env bash
# VISHWAAS — Full offline installer for Oracle Linux 10 (x86_64)
# Usage:
#   sudo ./install.sh controller   — set up the controller (admin/dashboard machine)
#   sudo ./install.sh agent        — set up the agent (VPN node machine)
#
# After install, start with:
#   controller:  cd /opt/vishwaas/controller && ./start_controller.sh
#   agent:       cd /opt/vishwaas/agent      && sudo ./start_agent.sh
set -e

PACK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="${1:-}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[✗]${NC} $*"; exit 1; }
step()  { echo -e "\n${YELLOW}━━ $* ━━${NC}"; }

# ── Root check ────────────────────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && error "Run as root: sudo ./install.sh $MODE"

# ── Mode check ────────────────────────────────────────────────────────────────
if [[ "$MODE" != "controller" && "$MODE" != "agent" ]]; then
    echo "Usage: sudo ./install.sh <controller|agent>"
    echo ""
    echo "  controller  — set up on the central admin/dashboard machine"
    echo "  agent       — set up on each VPN node machine"
    exit 1
fi

# ── 1. Install RPMs (fully offline — no repo required) ───────────────────────
step "Installing system packages from local repo"

REPO_DIR="$PACK_DIR/repo"

if [[ "$MODE" == "controller" ]]; then
    PKGS_NEEDED=("python3" "python3-pip" "nginx")
else
    PKGS_NEEDED=("python3" "python3-pip" "wireguard-tools")
fi

# Check which packages still need installing
RPMS_TO_INSTALL=()
for pkg in "${PKGS_NEEDED[@]}"; do
    if rpm -q "$pkg" &>/dev/null; then
        info "$pkg already installed"
    else
        RPMS_TO_INSTALL+=("$pkg")
    fi
done

if [[ ${#RPMS_TO_INSTALL[@]} -gt 0 ]]; then
    # Install all RPMs in repo/ at once — dnf resolves deps from the local folder
    dnf install -y --nogpgcheck --disablerepo='*' "$REPO_DIR"/*.rpm \
        2>&1 | grep -v "^$\|metadata\|Loaded\|Loading\|mirror" || true
    info "System packages installed from local repo"
fi

# ── 2. WireGuard kernel module check ─────────────────────────────────────────
if [[ "$MODE" == "agent" ]]; then
    if ! modinfo wireguard &>/dev/null; then
        warn "WireGuard kernel module not loaded — trying modprobe"
        modprobe wireguard 2>/dev/null && info "WireGuard module loaded" || \
            warn "Could not load wireguard module. If kernel < 5.6, install kernel-modules-extra."
    else
        info "WireGuard kernel module available"
    fi
fi

# ── 3. Controller setup ───────────────────────────────────────────────────────
if [[ "$MODE" == "controller" ]]; then

    INSTALL_DIR="/opt/vishwaas/controller"
    step "Setting up controller in $INSTALL_DIR"

    mkdir -p "$INSTALL_DIR"/{backend,frontend/dist,logs}

    rsync -a --delete \
        --exclude='__pycache__' --exclude='*.pyc' --exclude='.venv' \
        --exclude='*.db' --exclude='.env' \
        "$PACK_DIR/controller/backend/" "$INSTALL_DIR/backend/"

    rsync -a --delete \
        "$PACK_DIR/controller/frontend/dist/" "$INSTALL_DIR/frontend/dist/"

    cp "$PACK_DIR/controller/start_controller.sh" "$INSTALL_DIR/"
    cp "$PACK_DIR/controller/nginx.conf" "$INSTALL_DIR/"
    chmod +x "$INSTALL_DIR/start_controller.sh"

    # Python venv + offline pip install
    step "Setting up Python virtual environment (offline)"
    if [[ ! -d "$INSTALL_DIR/backend/.venv" ]]; then
        python3 -m venv "$INSTALL_DIR/backend/.venv"
    fi
    "$INSTALL_DIR/backend/.venv/bin/pip" install --quiet --upgrade pip \
        --no-index --find-links="$PACK_DIR/controller/pip_packages"
    "$INSTALL_DIR/backend/.venv/bin/pip" install --quiet \
        --no-index --find-links="$PACK_DIR/controller/pip_packages" \
        -r "$INSTALL_DIR/backend/requirements.txt"
    info "Python dependencies installed"

    # .env setup
    step "Configuring controller"
    if [[ ! -f "$INSTALL_DIR/backend/.env" ]]; then
        cp "$INSTALL_DIR/backend/.env.example" "$INSTALL_DIR/backend/.env"
        AGENT_TOKEN=$(openssl rand -hex 32)
        JWT_SECRET=$(openssl rand -hex 32)
        sed -i "s|your-secret-token-here|$AGENT_TOKEN|" "$INSTALL_DIR/backend/.env"
        sed -i "s|change-me-in-production|$JWT_SECRET|" "$INSTALL_DIR/backend/.env"
    else
        AGENT_TOKEN=$(grep VISHWAAS_AGENT_TOKEN "$INSTALL_DIR/backend/.env" | cut -d= -f2)
        info ".env already exists — keeping existing config"
    fi

    # nginx — serve pre-built frontend + proxy API
    step "Configuring nginx"
    CONTROLLER_IP=$(hostname -I | awk '{print $1}')
    cat > /etc/nginx/conf.d/vishwaas.conf <<NGINXEOF
server {
    listen 80;
    server_name _;

    root $INSTALL_DIR/frontend/dist;
    index index.html;

    location / {
        try_files \$uri \$uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_read_timeout 60s;
    }
}
NGINXEOF
    nginx -t && systemctl enable --now nginx && info "nginx configured and started" || \
        warn "nginx config test failed — check /etc/nginx/conf.d/vishwaas.conf"

    # Firewall
    step "Opening firewall ports"
    if systemctl is-active firewalld &>/dev/null; then
        firewall-cmd --permanent --add-service=http &>/dev/null || true
        firewall-cmd --permanent --add-port=8000/tcp &>/dev/null || true
        firewall-cmd --reload &>/dev/null
        info "Firewall: ports 80 and 8000 opened"
    else
        warn "firewalld not running — skipping firewall config"
    fi

    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}  VISHWAAS Controller ready!${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "  Install dir: $INSTALL_DIR"
    echo "  Config:      $INSTALL_DIR/backend/.env"
    echo ""
    echo "  VISHWAAS_AGENT_TOKEN=$AGENT_TOKEN"
    echo "  (copy this token into each agent's agent_config.json)"
    echo ""
    echo "  ── Start the controller ──────────────────────────────────"
    echo "  cd $INSTALL_DIR"
    echo "  ./start_controller.sh"
    echo ""
    echo "  Dashboard will be at: http://$CONTROLLER_IP/"
    echo "  API health check:     http://$CONTROLLER_IP:8000/health"
    echo ""
fi

# ── 4. Agent setup ────────────────────────────────────────────────────────────
if [[ "$MODE" == "agent" ]]; then

    INSTALL_DIR="/opt/vishwaas/agent"
    step "Setting up agent in $INSTALL_DIR"

    mkdir -p "$INSTALL_DIR"

    rsync -a --delete \
        --exclude='__pycache__' --exclude='*.pyc' --exclude='venv' \
        --exclude='keys' --exclude='agent_config.json' \
        "$PACK_DIR/agent/" "$INSTALL_DIR/"
    chmod +x "$INSTALL_DIR/start_agent.sh"

    # Python venv + offline pip install
    step "Setting up Python virtual environment (offline)"
    if [[ ! -d "$INSTALL_DIR/venv" ]]; then
        python3 -m venv "$INSTALL_DIR/venv"
    fi
    "$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip \
        --no-index --find-links="$PACK_DIR/agent/pip_packages"
    "$INSTALL_DIR/venv/bin/pip" install --quiet \
        --no-index --find-links="$PACK_DIR/agent/pip_packages" \
        -r "$INSTALL_DIR/requirements.txt"
    info "Python dependencies installed"

    # Keys directory
    mkdir -p /etc/vishwaas/keys
    chmod 700 /etc/vishwaas/keys

    # Config
    step "Configuring agent"
    if [[ ! -f "$INSTALL_DIR/agent_config.json" ]]; then
        cp "$INSTALL_DIR/agent_config.json.example" "$INSTALL_DIR/agent_config.json"
        # Pre-fill agent_advertise_url with this machine's IP
        THIS_IP=$(hostname -I | awk '{print $1}')
        sed -i "s|http://THIS_MACHINE_IP:9000|http://$THIS_IP:9000|" \
            "$INSTALL_DIR/agent_config.json"
    else
        info "agent_config.json already exists — keeping existing config"
    fi

    # Firewall
    step "Opening firewall ports"
    if systemctl is-active firewalld &>/dev/null; then
        firewall-cmd --permanent --add-port=9000/tcp &>/dev/null || true
        firewall-cmd --permanent --add-port=51820/udp &>/dev/null || true
        firewall-cmd --reload &>/dev/null
        info "Firewall: ports 9000/tcp and 51820/udp opened"
    else
        warn "firewalld not running — skipping firewall config"
    fi

    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}  VISHWAAS Agent ready!${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "  Install dir: $INSTALL_DIR"
    echo ""
    echo "  ── 1. Edit config ────────────────────────────────────────"
    echo "  nano $INSTALL_DIR/agent_config.json"
    echo ""
    echo "  Fill in:"
    echo "    master_url    — http://<controller-ip>:8000"
    echo "    master_token  — VISHWAAS_AGENT_TOKEN from the controller"
    echo ""
    echo "  ── 2. Start the agent ────────────────────────────────────"
    echo "  cd $INSTALL_DIR"
    echo "  sudo ./start_agent.sh"
    echo ""
    echo "  Then approve the join request on the controller dashboard."
    echo ""
fi
