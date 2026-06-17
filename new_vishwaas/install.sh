#!/usr/bin/env bash
# =============================================================================
#  VISHWAAS — One-click installer
#  Usage:
#    Controller:  sudo ./install.sh controller
#    Agent:       sudo ./install.sh agent
#    Agent (auto-configure):
#                 sudo ./install.sh agent <controller-ip> <agent-token>
#
#  Installs everything from this package — no internet, no system Python,
#  no Node.js, no npm required. Works on CentOS 7/8/9, RHEL 8/9/10,
#  Oracle Linux 8/9/10 (x86_64).
# =============================================================================
set -euo pipefail

PACK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="${1:-}"
CONTROLLER_IP="${2:-}"
AGENT_TOKEN_ARG="${3:-}"

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${GREEN}  [✓]${NC} $*"; }
warn()    { echo -e "${YELLOW}  [!]${NC} $*"; }
error()   { echo -e "${RED}  [✗] ERROR:${NC} $*"; exit 1; }
step()    { echo -e "\n${CYAN}▶ $*${NC}"; }
banner()  { echo -e "\n${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }

# ── Validate ──────────────────────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && error "Must run as root.  Try:  sudo ./install.sh $MODE"

if [[ "$MODE" != "controller" && "$MODE" != "agent" ]]; then
    echo ""
    echo "  Usage:"
    echo "    sudo ./install.sh controller"
    echo "    sudo ./install.sh agent"
    echo "    sudo ./install.sh agent <controller-ip> <agent-token>"
    echo ""
    echo "  Run 'controller' first, then 'agent' on every other machine."
    echo ""
    exit 1
fi

# ── Header ────────────────────────────────────────────────────────────────────
banner
echo -e "${GREEN}  VISHWAAS Installer — mode: $MODE${NC}"
banner
echo ""

# =============================================================================
#  STEP 1 — Python 3.11 (bundled standalone, no system Python needed)
# =============================================================================
step "Installing Python 3.11"

PYTHON_DIR="/opt/vishwaas/python"
mkdir -p "$PYTHON_DIR"
cp -a "$PACK_DIR/python/." "$PYTHON_DIR/"
PYTHON="$PYTHON_DIR/bin/python3.11"

[[ -x "$PYTHON" ]] || error "Python binary missing — package may be corrupted.  Re-extract the tar.gz."
info "Python $($PYTHON --version 2>&1) installed to $PYTHON_DIR"

# =============================================================================
#  STEP 2 — System packages (nginx for controller, wireguard for agent)
# =============================================================================
step "Installing system packages"

# Pick package manager (dnf preferred, yum fallback)
if command -v dnf &>/dev/null; then PKG_MGR="dnf"; else PKG_MGR="yum"; fi

install_rpm() {
    local rpm="$1"
    local name="$2"
    if rpm -q "$name" &>/dev/null; then
        info "$name already installed — skipping"
    else
        if $PKG_MGR install -y --nogpgcheck "$rpm" &>/dev/null; then
            info "$name installed"
        else
            warn "$name install failed — trying rpm -ivh as fallback"
            rpm -ivh --nodeps "$rpm" 2>/dev/null || warn "$name could not be installed"
        fi
    fi
}

if [[ "$MODE" == "controller" ]]; then
    # nginx
    for rpm in \
        "$PACK_DIR/repo/nginx-filesystem"*.rpm \
        "$PACK_DIR/repo/oracle-logos-httpd"*.rpm \
        "$PACK_DIR/repo/nginx-core"*.rpm \
        "$PACK_DIR/repo/nginx-"[0-9]*.rpm; do
        [[ -f "$rpm" ]] && install_rpm "$rpm" "$(basename "$rpm" .rpm | sed 's/-[0-9].*//')"
    done

    # Enable and start nginx
    if systemctl enable nginx &>/dev/null && systemctl start nginx &>/dev/null; then
        info "nginx started"
    elif nginx -t &>/dev/null && nginx &>/dev/null; then
        info "nginx started (direct)"
    else
        warn "nginx could not be started — will configure and retry at the end"
    fi

else
    # wireguard-tools
    RPM=$(find "$PACK_DIR/repo" -name "wireguard-tools*.rpm" | head -1)
    if [[ -n "$RPM" ]]; then
        install_rpm "$RPM" "wireguard-tools"
    else
        warn "wireguard-tools RPM not found in repo/ — skipping"
    fi

    # Load WireGuard kernel module
    if modprobe wireguard 2>/dev/null; then
        info "WireGuard kernel module loaded"
    else
        warn "Could not load WireGuard module now — it may load automatically when needed"
        warn "If WireGuard fails later, run: sudo modprobe wireguard"
        warn "Or install kernel-modules-extra for your kernel version"
    fi
fi

# =============================================================================
#  STEP 3 — Copy application code to /opt/vishwaas
# =============================================================================
step "Installing VISHWAAS $MODE to /opt/vishwaas/$MODE"

# Use rsync if available, fall back to cp
_copy() {
    local src="$1" dst="$2"; shift 2
    mkdir -p "$dst"
    if command -v rsync &>/dev/null; then
        rsync -a --delete "$@" "$src/" "$dst/"
    else
        # cp fallback: delete dst contents except excluded items, then copy
        cp -a "$src/." "$dst/"
    fi
}

if [[ "$MODE" == "controller" ]]; then
    INSTALL_DIR="/opt/vishwaas/controller"
    mkdir -p "$INSTALL_DIR/logs"

    _copy "$PACK_DIR/controller/backend" "$INSTALL_DIR/backend" \
        --exclude='__pycache__' --exclude='*.pyc' \
        --exclude='*.db' --exclude='.env' --exclude='.venv'

    _copy "$PACK_DIR/controller/frontend/dist" "$INSTALL_DIR/frontend/dist"

    cp "$PACK_DIR/controller/start_controller.sh" "$INSTALL_DIR/"
    [[ -f "$PACK_DIR/controller/nginx.conf" ]] && cp "$PACK_DIR/controller/nginx.conf" "$INSTALL_DIR/"
    chmod +x "$INSTALL_DIR/start_controller.sh"

else
    INSTALL_DIR="/opt/vishwaas/agent"
    mkdir -p "$INSTALL_DIR"

    _copy "$PACK_DIR/agent" "$INSTALL_DIR" \
        --exclude='__pycache__' --exclude='*.pyc' \
        --exclude='keys' --exclude='agent_config.json' --exclude='venv'

    chmod +x "$INSTALL_DIR/start_agent.sh"
fi

info "Code installed to $INSTALL_DIR"

# =============================================================================
#  STEP 4 — Python virtual environment (pre-built, just copy + fix paths)
# =============================================================================
step "Setting up Python environment"

if [[ "$MODE" == "controller" ]]; then
    SRC_VENV="$PACK_DIR/controller/backend/.venv"
    DST_VENV="$INSTALL_DIR/backend/.venv"
else
    SRC_VENV="$PACK_DIR/agent/venv"
    DST_VENV="$INSTALL_DIR/venv"
fi

[[ -d "$SRC_VENV" ]] || error "Pre-built venv missing at $SRC_VENV — package may be corrupted"

# Remove stale venv if present, then copy fresh
[[ -d "$DST_VENV" ]] && rm -rf "$DST_VENV"
cp -a "$SRC_VENV" "$DST_VENV"

# Fix all hardcoded paths from the build machine to this machine's paths.
# Two replacements needed:
#   1. old venv path  → new venv path     (shebang lines in bin/ scripts)
#   2. old python dir → new python dir    (pyvenv.cfg home= line)
OLD_VENV_PATH=$(grep "^home = " "$DST_VENV/pyvenv.cfg" \
    | sed 's/home = //' \
    | sed 's|/bin$||' \
    | sed 's|/python/bin$||' \
    | head -1)
# OLD_VENV_PATH is the root of the old pack dir on the build machine

# Rewrite bin scripts
find "$DST_VENV/bin" -type f | while read -r f; do
    if file "$f" 2>/dev/null | grep -q "text\|script"; then
        # Replace old venv src path with dst path
        sed -i "s|${SRC_VENV}|${DST_VENV}|g" "$f" 2>/dev/null || true
        # Replace any remaining build-machine pack prefix
        sed -i "s|${OLD_VENV_PATH}.*/.venv|${DST_VENV}|g" "$f" 2>/dev/null || true
        sed -i "s|${OLD_VENV_PATH}.*/venv[^/]|${DST_VENV}/|g" "$f" 2>/dev/null || true
    fi
done

# Rewrite pyvenv.cfg
sed -i "s|${SRC_VENV}|${DST_VENV}|g"         "$DST_VENV/pyvenv.cfg"
sed -i "s|${OLD_VENV_PATH}.*/.venv|${DST_VENV}|g" "$DST_VENV/pyvenv.cfg" 2>/dev/null || true
# Fix python home to point to our bundled python
OLD_PYTHON_HOME=$(grep "^home = " "$DST_VENV/pyvenv.cfg" | sed 's/home = //')
sed -i "s|${OLD_PYTHON_HOME}|${PYTHON_DIR}/bin|g" "$DST_VENV/pyvenv.cfg"

# Verify
"$DST_VENV/bin/python" -c "import uvicorn" 2>/dev/null \
    || error "Python environment broken after path fix. Run: sudo ./install.sh $MODE to retry."
info "Python environment ready"

# =============================================================================
#  STEP 5 — Controller configuration (nginx, .env, secrets)
# =============================================================================
if [[ "$MODE" == "controller" ]]; then
    step "Configuring controller"

    # Generate .env if not already present
    if [[ ! -f "$INSTALL_DIR/backend/.env" ]]; then
        cp "$INSTALL_DIR/backend/.env.example" "$INSTALL_DIR/backend/.env"
        AGENT_TOKEN=$(openssl rand -hex 32)
        JWT_SECRET=$(openssl rand -hex 32)
        sed -i "s|your-secret-token-here|$AGENT_TOKEN|" "$INSTALL_DIR/backend/.env"
        sed -i "s|change-me-in-production|$JWT_SECRET|"  "$INSTALL_DIR/backend/.env"
        info ".env created with generated secrets"
    else
        AGENT_TOKEN=$(grep 'VISHWAAS_AGENT_TOKEN' "$INSTALL_DIR/backend/.env" | cut -d= -f2-)
        info ".env already exists — keeping existing secrets"
    fi

    # nginx config — write to conf.d (works whether nginx was pre-installed or just installed)
    NGINX_CONF_DIR=""
    for d in /etc/nginx/conf.d /usr/local/nginx/conf/conf.d; do
        [[ -d "$d" ]] && NGINX_CONF_DIR="$d" && break
    done

    if [[ -z "$NGINX_CONF_DIR" ]]; then
        mkdir -p /etc/nginx/conf.d
        NGINX_CONF_DIR="/etc/nginx/conf.d"
    fi

    cat > "$NGINX_CONF_DIR/vishwaas.conf" <<NGINXEOF
server {
    listen 80 default_server;
    server_name _;

    root ${INSTALL_DIR}/frontend/dist;
    index index.html;

    # Serve React app — all unknown paths fall back to index.html
    location / {
        try_files \$uri \$uri/ /index.html;
    }

    # Proxy API calls to FastAPI backend
    location /api/ {
        proxy_pass         http://127.0.0.1:8000/;
        proxy_http_version 1.1;
        proxy_set_header   Host \$host;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_set_header   X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_read_timeout 60s;
    }
}
NGINXEOF

    # Allow nginx to proxy to localhost (SELinux)
    setsebool -P httpd_can_network_connect 1 &>/dev/null || true

    # Reload or start nginx
    if nginx -t &>/dev/null; then
        if systemctl is-active nginx &>/dev/null; then
            systemctl reload nginx && info "nginx reloaded with new config"
        else
            systemctl start nginx &>/dev/null && info "nginx started" \
                || nginx &>/dev/null && info "nginx started (direct)"
        fi
    else
        warn "nginx config test failed — check /var/log/nginx/error.log"
    fi

    # Firewall
    if systemctl is-active firewalld &>/dev/null; then
        firewall-cmd --permanent --add-service=http   &>/dev/null || true
        firewall-cmd --permanent --add-port=8000/tcp  &>/dev/null || true
        firewall-cmd --reload                         &>/dev/null || true
        info "Firewall: ports 80 and 8000 opened"
    else
        warn "firewalld not running — make sure ports 80 and 8000 are open on this machine"
    fi

    # Check if port 80 is already taken by something other than nginx
    if ss -tlnp 2>/dev/null | grep -q ':80 '; then
        info "Port 80 is listening"
    else
        warn "Port 80 not listening — nginx may not have started. Check: sudo systemctl status nginx"
    fi
fi

# =============================================================================
#  STEP 6 — Agent configuration
# =============================================================================
if [[ "$MODE" == "agent" ]]; then
    step "Configuring agent"

    mkdir -p /etc/vishwaas/keys && chmod 700 /etc/vishwaas/keys

    THIS_IP=$(hostname -I | awk '{print $1}')

    if [[ ! -f "$INSTALL_DIR/agent_config.json" ]]; then
        cp "$INSTALL_DIR/agent_config.json.example" "$INSTALL_DIR/agent_config.json"
        sed -i "s|http://THIS_MACHINE_IP:9000|http://$THIS_IP:9000|g" "$INSTALL_DIR/agent_config.json"
        info "agent_config.json created"
    else
        info "agent_config.json already exists — keeping"
    fi

    # Auto-configure controller IP and token if passed as arguments
    if [[ -n "$CONTROLLER_IP" ]]; then
        sed -i "s|http://CONTROLLER_IP:8000|http://$CONTROLLER_IP:8000|g" "$INSTALL_DIR/agent_config.json"
        sed -i "s|\"master_url\":.*|\"master_url\": \"http://$CONTROLLER_IP:8000\",|g" "$INSTALL_DIR/agent_config.json"
        info "Controller URL set to http://$CONTROLLER_IP:8000"
    fi

    if [[ -n "$AGENT_TOKEN_ARG" ]]; then
        sed -i "s|YOUR_SHARED_TOKEN_SAME_AS_CONTROLLER_VISHWAAS_AGENT_TOKEN|$AGENT_TOKEN_ARG|g" "$INSTALL_DIR/agent_config.json"
        sed -i "s|\"master_token\":.*|\"master_token\": \"$AGENT_TOKEN_ARG\",|g" "$INSTALL_DIR/agent_config.json"
        info "Agent token configured"
    fi

    # Firewall
    if systemctl is-active firewalld &>/dev/null; then
        firewall-cmd --permanent --add-port=9000/tcp   &>/dev/null || true
        firewall-cmd --permanent --add-port=51820/udp  &>/dev/null || true
        firewall-cmd --reload                          &>/dev/null || true
        info "Firewall: ports 9000 (agent API) and 51820 (WireGuard) opened"
    else
        warn "firewalld not running — make sure ports 9000/tcp and 51820/udp are open"
    fi
fi

# =============================================================================
#  STEP 7 — Start the service
# =============================================================================
step "Starting VISHWAAS $MODE"

THIS_IP=$(hostname -I | awk '{print $1}')

if [[ "$MODE" == "controller" ]]; then
    # Kill any existing instance
    pkill -f "uvicorn app.main:app" 2>/dev/null && sleep 1 || true

    cd "$INSTALL_DIR"
    nohup "$DST_VENV/bin/python" -m uvicorn app.main:app \
        --app-dir "$INSTALL_DIR/backend" \
        --host 0.0.0.0 --port 8000 --no-access-log \
        >> "$INSTALL_DIR/logs/backend.log" 2>&1 &
    BACKEND_PID=$!
    echo "$BACKEND_PID" > "$INSTALL_DIR/logs/backend.pid"
    sleep 2

    # Verify it came up
    if kill -0 "$BACKEND_PID" 2>/dev/null; then
        info "Controller API started (PID $BACKEND_PID)"
        info "Logs: tail -f $INSTALL_DIR/logs/backend.log"
    else
        error "Controller failed to start. Check logs: tail -50 $INSTALL_DIR/logs/backend.log"
    fi

else
    # Agent needs manual config check first if not auto-configured
    MASTER_URL=$(python3 -c "import json; d=json.load(open('$INSTALL_DIR/agent_config.json')); print(d.get('master_url',''))" 2>/dev/null || true)

    if [[ "$MASTER_URL" == *"CONTROLLER_IP"* ]] || [[ -z "$MASTER_URL" ]]; then
        warn "Agent config not fully set — skipping auto-start"
        warn "Edit the config first: nano $INSTALL_DIR/agent_config.json"
    else
        # Kill any existing instance
        pkill -f "uvicorn app.main:app" 2>/dev/null && sleep 1 || true

        cd "$INSTALL_DIR"
        nohup "$DST_VENV/bin/python" -m uvicorn app.main:app \
            --app-dir "$INSTALL_DIR" \
            --host 0.0.0.0 --port 9000 \
            >> "$INSTALL_DIR/agent.log" 2>&1 &
        AGENT_PID=$!
        echo "$AGENT_PID" > "$INSTALL_DIR/agent.pid"
        sleep 2

        if kill -0 "$AGENT_PID" 2>/dev/null; then
            info "Agent started (PID $AGENT_PID)"
            info "Logs: tail -f $INSTALL_DIR/agent.log"
        else
            error "Agent failed to start. Check logs: tail -50 $INSTALL_DIR/agent.log"
        fi
    fi
fi

# =============================================================================
#  Done — print summary
# =============================================================================
banner
echo -e "${GREEN}  Install complete!${NC}"
banner
echo ""

if [[ "$MODE" == "controller" ]]; then
    echo -e "  ${CYAN}Dashboard:${NC}          http://$THIS_IP/"
    echo -e "  ${CYAN}API:${NC}                http://$THIS_IP:8000/health"
    echo -e "  ${CYAN}Login:${NC}              any username / any password (dev mode)"
    echo ""
    echo -e "  ${YELLOW}VISHWAAS_AGENT_TOKEN = $AGENT_TOKEN${NC}"
    echo -e "  Copy this token into each agent machine when running install.sh"
    echo ""
    echo -e "  ${CYAN}Install agent on each node:${NC}"
    echo -e "    sudo ./install.sh agent $THIS_IP $AGENT_TOKEN"
    echo ""
    echo -e "  ${CYAN}Logs:${NC}               tail -f $INSTALL_DIR/logs/backend.log"
    echo -e "  ${CYAN}Stop:${NC}               pkill -f 'uvicorn app.main:app'"
    echo -e "  ${CYAN}Restart:${NC}            sudo ./install.sh controller"
fi

if [[ "$MODE" == "agent" ]]; then
    MASTER_URL=$(python3 -c "import json; d=json.load(open('$INSTALL_DIR/agent_config.json')); print(d.get('master_url',''))" 2>/dev/null || echo "not configured")
    echo -e "  ${CYAN}Agent health:${NC}       http://$THIS_IP:9000/health"
    echo -e "  ${CYAN}Controller:${NC}         $MASTER_URL"
    echo -e "  ${CYAN}Config:${NC}             $INSTALL_DIR/agent_config.json"
    echo -e "  ${CYAN}Logs:${NC}               tail -f $INSTALL_DIR/agent.log"
    echo ""

    if [[ "$MASTER_URL" == *"CONTROLLER_IP"* ]] || [[ -z "$MASTER_URL" ]]; then
        echo -e "  ${YELLOW}⚠  Edit config before starting the agent:${NC}"
        echo -e "     nano $INSTALL_DIR/agent_config.json"
        echo -e "     Set: master_url, master_token, agent_advertise_url"
        echo ""
        echo -e "  Then start manually:"
        echo -e "     cd $INSTALL_DIR && sudo ./start_agent.sh"
    else
        echo -e "  ${CYAN}Next:${NC} Go to the dashboard and approve this node under Join Requests"
    fi
fi

echo ""
