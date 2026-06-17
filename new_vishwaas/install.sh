#!/usr/bin/env bash
# =============================================================================
#  VISHWAAS — One-click installer
#
#  Usage:
#    Controller:               sudo ./install.sh controller
#    Agent (manual config):    sudo ./install.sh agent
#    Agent (auto-configure):   sudo ./install.sh agent <controller-ip> <token>
#
#  Safe to re-run — existing .env and agent_config.json are never overwritten.
#  Works on CentOS 7/8/9, RHEL 8/9/10, Oracle Linux 8/9/10 (x86_64).
#  Requires nothing pre-installed — Python, nginx, libraries all bundled.
# =============================================================================
set -uo pipefail   # note: no -e so we control every failure explicitly

PACK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="${1:-}"
CONTROLLER_IP="${2:-}"
AGENT_TOKEN_ARG="${3:-}"

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()   { echo -e "${GREEN}  [✓]${NC} $*"; }
warn()   { echo -e "${YELLOW}  [!]${NC} $*"; }
error()  { echo -e "${RED}  [✗] ERROR:${NC} $*"; exit 1; }
step()   { echo -e "\n${CYAN}▶ $*${NC}"; }
banner() { echo -e "\n${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }

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

banner
echo -e "${GREEN}  VISHWAAS Installer — mode: $MODE${NC}"
banner
echo ""

# =============================================================================
#  STEP 1 — Bundled Python 3.11
# =============================================================================
step "Installing Python 3.11"

PYTHON_DIR="/opt/vishwaas/python"
mkdir -p "$PYTHON_DIR"
cp -a "$PACK_DIR/python/." "$PYTHON_DIR/"
PYTHON="$PYTHON_DIR/bin/python3.11"

[[ -x "$PYTHON" ]] || error "Python binary missing — re-extract the tar.gz and retry."
info "Python $($PYTHON --version 2>&1) ready at $PYTHON_DIR"

# Helper: read a JSON field using our bundled Python (no system python3 needed)
json_get() { "$PYTHON" -c "import json,sys; d=json.load(open('$1')); print(d.get('$2',''))" 2>/dev/null || true; }

# =============================================================================
#  STEP 2 — Pre-flight: check for port conflicts before touching anything
# =============================================================================
step "Checking for port conflicts"

check_port() {
    local port="$1" label="$2"
    # ss is preferred; fall back to netstat
    if ss -tlnp 2>/dev/null | grep -q ":${port} "; then
        local owner
        owner=$(ss -tlnp 2>/dev/null | grep ":${port} " | grep -oP 'users:\(\("\K[^"]+' | head -1 || true)
        warn "Port $port ($label) is already in use by: ${owner:-unknown process}"
        return 1
    fi
    return 0
}

PORT_CONFLICT=0
if [[ "$MODE" == "controller" ]]; then
    check_port 8000 "controller API"  || PORT_CONFLICT=1
    # Port 80 may be taken by httpd/apache — we handle that below, not a hard fail
else
    check_port 9000 "agent API"       || PORT_CONFLICT=1
fi

if [[ $PORT_CONFLICT -eq 1 ]]; then
    warn "A port conflict was detected above."
    warn "The installer will kill any existing VISHWAAS process and retry."
    warn "If something else owns the port, stop it first and re-run."
fi

# =============================================================================
#  STEP 3 — Stop any running VISHWAAS process (clean slate for upgrade)
# =============================================================================
step "Stopping any existing VISHWAAS process"

TARGET_PORT=$( [[ "$MODE" == "controller" ]] && echo 8000 || echo 9000 )

# Kill by PID file first (cleanest)
PID_FILE=$( [[ "$MODE" == "controller" ]] \
    && echo "/opt/vishwaas/controller/logs/backend.pid" \
    || echo "/opt/vishwaas/agent/agent.pid" )

if [[ -f "$PID_FILE" ]]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        kill "$OLD_PID" 2>/dev/null || true
        sleep 1
        kill -9 "$OLD_PID" 2>/dev/null || true
        info "Stopped previous process (PID $OLD_PID)"
    fi
    rm -f "$PID_FILE"
fi

# Belt-and-suspenders: kill anything still holding the target port
if ss -tlnp 2>/dev/null | grep -q ":${TARGET_PORT} "; then
    PIDS=$(ss -tlnp 2>/dev/null | grep ":${TARGET_PORT} " | grep -oP 'pid=\K\d+' || true)
    for pid in $PIDS; do
        kill -9 "$pid" 2>/dev/null && warn "Force-killed PID $pid holding port $TARGET_PORT" || true
    done
    sleep 1
fi

# Also kill by process name pattern (catches leftover screen/nohup sessions)
pkill -f "uvicorn app.main:app" 2>/dev/null || true
sleep 1
info "Port $TARGET_PORT is free"

# =============================================================================
#  STEP 4 — System packages (nginx / wireguard-tools)
# =============================================================================
step "Installing system packages"

if command -v dnf &>/dev/null; then PKG_MGR="dnf"; else PKG_MGR="yum"; fi

install_rpm() {
    local rpm_file="$1"
    local pkg_name="$2"
    local installed_ver bundled_ver

    if rpm -q "$pkg_name" &>/dev/null; then
        installed_ver=$(rpm -q --queryformat '%{VERSION}' "$pkg_name" 2>/dev/null || echo "unknown")
        bundled_ver=$(rpm -qp --queryformat '%{VERSION}' "$rpm_file" 2>/dev/null || echo "unknown")

        if [[ "$installed_ver" == "$bundled_ver" ]]; then
            info "$pkg_name $installed_ver already installed — skipping"
        else
            warn "$pkg_name installed version ($installed_ver) differs from bundled ($bundled_ver) — upgrading"
            if $PKG_MGR install -y --nogpgcheck "$rpm_file" &>/dev/null; then
                info "$pkg_name upgraded to $bundled_ver"
            else
                rpm -Uvh --nodeps --force "$rpm_file" 2>/dev/null \
                    && info "$pkg_name upgraded (rpm -Uvh)" \
                    || warn "$pkg_name upgrade failed — continuing with installed version"
            fi
        fi
    else
        if $PKG_MGR install -y --nogpgcheck "$rpm_file" &>/dev/null; then
            info "$pkg_name installed"
        else
            rpm -ivh --nodeps "$rpm_file" 2>/dev/null \
                && info "$pkg_name installed (rpm -ivh)" \
                || warn "$pkg_name could not be installed — continuing anyway"
        fi
    fi
}

if [[ "$MODE" == "controller" ]]; then
    # Stop Apache/httpd if running on port 80 — it will conflict with nginx
    if systemctl is-active httpd &>/dev/null; then
        systemctl stop httpd &>/dev/null || true
        systemctl disable httpd &>/dev/null || true
        warn "Stopped and disabled httpd (Apache) — it was using port 80"
    fi
    if systemctl is-active apache2 &>/dev/null; then
        systemctl stop apache2 &>/dev/null || true
        systemctl disable apache2 &>/dev/null || true
        warn "Stopped and disabled apache2 — it was using port 80"
    fi

    # Install nginx RPMs in dependency order
    for rpm in \
        "$PACK_DIR/repo/nginx-filesystem"*.rpm \
        "$PACK_DIR/repo/oracle-logos-httpd"*.rpm \
        "$PACK_DIR/repo/nginx-core"*.rpm \
        "$PACK_DIR/repo/nginx-"[0-9]*.rpm; do
        [[ -f "$rpm" ]] || continue
        pkg=$(basename "$rpm" .rpm | sed 's/-[0-9].*//')
        install_rpm "$rpm" "$pkg"
    done

    systemctl enable nginx &>/dev/null || true
    if systemctl start nginx &>/dev/null; then
        info "nginx started"
    else
        warn "nginx systemctl start failed — will retry after config is written"
    fi

else
    RPM=$(find "$PACK_DIR/repo" -name "wireguard-tools*.rpm" 2>/dev/null | head -1)
    if [[ -n "$RPM" ]]; then
        install_rpm "$RPM" "wireguard-tools"
    else
        warn "wireguard-tools RPM not found in repo/ — skipping"
    fi

    # Bring down stale WireGuard interface from a previous run
    if ip link show wg0 &>/dev/null; then
        warn "WireGuard interface wg0 exists from a previous run — bringing it down"
        ip link delete wg0 2>/dev/null || wg-quick down wg0 2>/dev/null || true
        info "wg0 cleared"
    fi

    if modprobe wireguard 2>/dev/null; then
        info "WireGuard kernel module loaded"
    else
        warn "Could not load wireguard module — may auto-load when needed"
        warn "If VPN doesn't come up later: sudo modprobe wireguard"
    fi
fi

# =============================================================================
#  STEP 5 — Copy application code
# =============================================================================
step "Installing VISHWAAS $MODE code to /opt/vishwaas/$MODE"

# Safe copy: rsync with excludes, or manual cp that preserves protected files
_copy() {
    local src="$1" dst="$2"; shift 2
    mkdir -p "$dst"
    if command -v rsync &>/dev/null; then
        rsync -a --delete "$@" "$src/" "$dst/"
    else
        # No rsync — build exclusion list and copy manually
        local excludes=("$@")
        # Collect files/dirs to protect that already exist in dst
        local protected=()
        for excl in "${excludes[@]}"; do
            excl="${excl#--exclude=}"
            [[ -e "$dst/$excl" ]] && protected+=("$dst/$excl")
        done
        # Back up protected items to temp location
        local tmpdir
        tmpdir=$(mktemp -d)
        for p in "${protected[@]}"; do
            local rel="${p#$dst/}"
            mkdir -p "$tmpdir/$(dirname "$rel")"
            cp -a "$p" "$tmpdir/$rel" 2>/dev/null || true
        done
        # Full copy
        cp -a "$src/." "$dst/"
        # Restore protected items
        for p in "${protected[@]}"; do
            local rel="${p#$dst/}"
            [[ -e "$tmpdir/$rel" ]] && cp -a "$tmpdir/$rel" "$p" || true
        done
        rm -rf "$tmpdir"
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
    chmod +x "$INSTALL_DIR/start_controller.sh"
    [[ -f "$PACK_DIR/controller/nginx.conf" ]] && cp "$PACK_DIR/controller/nginx.conf" "$INSTALL_DIR/"

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
#  STEP 6 — Python venv (copy pre-built, fix hardcoded build-machine paths)
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

# Always replace the venv on install/upgrade — never leave a partial one
[[ -d "$DST_VENV" ]] && rm -rf "$DST_VENV"
cp -a "$SRC_VENV" "$DST_VENV"

# Read the paths baked into the venv at build time
BUILD_PYTHON_BIN=$(grep "^home = " "$DST_VENV/pyvenv.cfg" | sed 's/home = //' | tr -d '\r')
BUILD_VENV=$(grep "^home = " "$DST_VENV/pyvenv.cfg" \
    | sed 's/home = //' | sed 's|/python/bin$||' | tr -d '\r')
# BUILD_VENV is the pack root dir on the build machine (everything before /python/bin)

NEW_PYTHON_BIN="$PYTHON_DIR/bin"

# Rewrite every text file in venv/bin (shebang lines)
while IFS= read -r -d '' f; do
    if file "$f" 2>/dev/null | grep -qE "text|script|ASCII"; then
        # Replace build-time venv path with new install path
        sed -i "s|${SRC_VENV}|${DST_VENV}|g"                          "$f" 2>/dev/null || true
        # Replace any residual build-machine pack root + venv suffix
        sed -i "s|${BUILD_VENV}/controller/backend/.venv|${DST_VENV}|g" "$f" 2>/dev/null || true
        sed -i "s|${BUILD_VENV}/agent/venv|${DST_VENV}|g"               "$f" 2>/dev/null || true
        # Fix python interpreter path
        sed -i "s|${BUILD_PYTHON_BIN}|${NEW_PYTHON_BIN}|g"              "$f" 2>/dev/null || true
    fi
done < <(find "$DST_VENV/bin" -type f -print0)

# Rewrite pyvenv.cfg
sed -i "s|${SRC_VENV}|${DST_VENV}|g"                           "$DST_VENV/pyvenv.cfg"
sed -i "s|${BUILD_VENV}/controller/backend/.venv|${DST_VENV}|g" "$DST_VENV/pyvenv.cfg" 2>/dev/null || true
sed -i "s|${BUILD_VENV}/agent/venv|${DST_VENV}|g"               "$DST_VENV/pyvenv.cfg" 2>/dev/null || true
sed -i "s|${BUILD_PYTHON_BIN}|${NEW_PYTHON_BIN}|g"              "$DST_VENV/pyvenv.cfg"

# Verify — import something non-trivial to confirm the environment is healthy
if ! "$DST_VENV/bin/python" -c "import uvicorn, fastapi" 2>/dev/null; then
    warn "Pre-built venv import check failed — rebuilding from wheels"
    rm -rf "$DST_VENV"
    "$PYTHON" -m venv "$DST_VENV"
    if [[ "$MODE" == "controller" ]]; then
        WHEELS="$PACK_DIR/controller/pip_packages"
        REQS="$INSTALL_DIR/backend/requirements.txt"
    else
        WHEELS="$PACK_DIR/agent/pip_packages"
        REQS="$INSTALL_DIR/requirements.txt"
    fi
    "$DST_VENV/bin/pip" install --quiet --no-index --find-links="$WHEELS" -r "$REQS" \
        || error "pip install from bundled wheels failed — package may be corrupted"
    "$DST_VENV/bin/python" -c "import uvicorn, fastapi" \
        || error "Environment still broken after rebuild. Check logs above."
    info "Python environment rebuilt from wheels"
else
    info "Python environment ready (pre-built)"
fi

# =============================================================================
#  STEP 7 — Controller: .env, nginx, DB migration, firewall
# =============================================================================
if [[ "$MODE" == "controller" ]]; then
    step "Configuring controller"

    # .env — generate once, never overwrite
    if [[ ! -f "$INSTALL_DIR/backend/.env" ]]; then
        cp "$INSTALL_DIR/backend/.env.example" "$INSTALL_DIR/backend/.env"
        AGENT_TOKEN=$(openssl rand -hex 32)
        JWT_SECRET=$(openssl rand -hex 32)
        sed -i "s|your-secret-token-here|$AGENT_TOKEN|" "$INSTALL_DIR/backend/.env"
        sed -i "s|change-me-in-production|$JWT_SECRET|"  "$INSTALL_DIR/backend/.env"
        info ".env created with fresh secrets"
    else
        AGENT_TOKEN=$(grep 'VISHWAAS_AGENT_TOKEN' "$INSTALL_DIR/backend/.env" | cut -d= -f2- | tr -d '\r')
        info ".env already exists — keeping existing secrets"
    fi

    # DB migration (safe on first run and on upgrades)
    DB_FILE="$INSTALL_DIR/backend/vishwaas.db"
    if [[ -f "$DB_FILE" ]]; then
        info "Existing database found — running alembic migrations"
        (cd "$INSTALL_DIR/backend" && "$DST_VENV/bin/alembic" upgrade head 2>&1 | sed 's/^/    /') \
            && info "Database migrations applied" \
            || warn "Alembic migration had warnings — check the output above"
    else
        info "Fresh install — database will be created on first start"
    fi

    # nginx config — remove default_server from any other conf.d file to avoid conflicts
    NGINX_CONF_DIR="/etc/nginx/conf.d"
    mkdir -p "$NGINX_CONF_DIR"

    # Disable any other conf file that claims default_server on port 80
    for conf in "$NGINX_CONF_DIR"/*.conf; do
        [[ "$conf" == "$NGINX_CONF_DIR/vishwaas.conf" ]] && continue
        [[ -f "$conf" ]] || continue
        if grep -q "default_server" "$conf" 2>/dev/null; then
            mv "$conf" "${conf}.disabled"
            warn "Disabled conflicting nginx config: $conf (renamed to .disabled)"
        fi
    done

    # Also disable the default nginx welcome page if present
    [[ -f /etc/nginx/nginx.conf ]] && \
        sed -i 's|^\s*include /etc/nginx/conf\.d/\*\.conf;|    include /etc/nginx/conf.d/*.conf;|' \
        /etc/nginx/nginx.conf 2>/dev/null || true

    cat > "$NGINX_CONF_DIR/vishwaas.conf" <<NGINXEOF
server {
    listen 80 default_server;
    server_name _;

    root ${INSTALL_DIR}/frontend/dist;
    index index.html;

    location / {
        try_files \$uri \$uri/ /index.html;
    }

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

    # SELinux — allow nginx to proxy to localhost
    setsebool -P httpd_can_network_connect 1 &>/dev/null || true

    # Test and reload nginx
    if nginx -t 2>/tmp/nginx_test.log; then
        if systemctl is-active nginx &>/dev/null; then
            systemctl reload nginx && info "nginx reloaded"
        else
            systemctl start nginx && info "nginx started" \
                || warn "nginx start failed — check: sudo systemctl status nginx"
        fi
    else
        warn "nginx config test failed:"
        cat /tmp/nginx_test.log | sed 's/^/    /'
        warn "Fix nginx config then run: sudo nginx -t && sudo systemctl start nginx"
    fi

    # Firewall
    if systemctl is-active firewalld &>/dev/null; then
        firewall-cmd --permanent --add-service=http  &>/dev/null || true
        firewall-cmd --permanent --add-port=8000/tcp &>/dev/null || true
        firewall-cmd --reload                        &>/dev/null || true
        info "Firewall: ports 80 and 8000 opened"
    else
        warn "firewalld not active — ensure ports 80 and 8000 are open in your firewall"
    fi
fi

# =============================================================================
#  STEP 8 — Agent: config, firewall
# =============================================================================
if [[ "$MODE" == "agent" ]]; then
    step "Configuring agent"

    mkdir -p /etc/vishwaas/keys && chmod 700 /etc/vishwaas/keys
    THIS_IP=$(hostname -I | awk '{print $1}')

    # Create config from example if not present
    if [[ ! -f "$INSTALL_DIR/agent_config.json" ]]; then
        cp "$INSTALL_DIR/agent_config.json.example" "$INSTALL_DIR/agent_config.json"
        sed -i "s|http://THIS_MACHINE_IP:9000|http://$THIS_IP:9000|g" \
            "$INSTALL_DIR/agent_config.json"
        info "agent_config.json created"
    else
        info "agent_config.json exists — keeping (use -f flag to force overwrite)"
    fi

    # Always update advertise URL to current machine IP (handles IP changes)
    OLD_ADV=$(json_get "$INSTALL_DIR/agent_config.json" "agent_advertise_url")
    if [[ "$OLD_ADV" != "http://$THIS_IP:9000" && "$OLD_ADV" != *"THIS_MACHINE_IP"* ]]; then
        warn "agent_advertise_url was '$OLD_ADV' — updating to http://$THIS_IP:9000"
    fi
    sed -i "s|\"agent_advertise_url\":.*|\"agent_advertise_url\": \"http://$THIS_IP:9000\",|g" \
        "$INSTALL_DIR/agent_config.json"

    # Auto-configure controller IP and token if passed as arguments
    if [[ -n "$CONTROLLER_IP" ]]; then
        sed -i "s|\"master_url\":.*|\"master_url\": \"http://$CONTROLLER_IP:8000\",|g" \
            "$INSTALL_DIR/agent_config.json"
        info "Controller URL set to http://$CONTROLLER_IP:8000"
    fi
    if [[ -n "$AGENT_TOKEN_ARG" ]]; then
        sed -i "s|\"master_token\":.*|\"master_token\": \"$AGENT_TOKEN_ARG\",|g" \
            "$INSTALL_DIR/agent_config.json"
        info "Agent token configured"
    fi

    # Firewall
    if systemctl is-active firewalld &>/dev/null; then
        firewall-cmd --permanent --add-port=9000/tcp  &>/dev/null || true
        firewall-cmd --permanent --add-port=51820/udp &>/dev/null || true
        firewall-cmd --reload                         &>/dev/null || true
        info "Firewall: ports 9000/tcp and 51820/udp opened"
    else
        warn "firewalld not active — ensure ports 9000/tcp and 51820/udp are open"
    fi
fi

# =============================================================================
#  STEP 9 — Start the service
# =============================================================================
step "Starting VISHWAAS $MODE"

THIS_IP=$(hostname -I | awk '{print $1}')

if [[ "$MODE" == "controller" ]]; then
    LOG="$INSTALL_DIR/logs/backend.log"
    PID_FILE="$INSTALL_DIR/logs/backend.pid"

    cd "$INSTALL_DIR/backend"
    nohup "$DST_VENV/bin/python" -m uvicorn app.main:app \
        --host 0.0.0.0 --port 8000 --no-access-log \
        >> "$LOG" 2>&1 &
    echo $! > "$PID_FILE"
    sleep 3

    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        # Double-check it's actually responding
        if "$PYTHON" -c "
import urllib.request, sys, time
for i in range(5):
    try:
        urllib.request.urlopen('http://localhost:8000/health', timeout=2)
        sys.exit(0)
    except:
        time.sleep(1)
sys.exit(1)
" 2>/dev/null; then
            info "Controller API started and responding (PID $PID)"
        else
            warn "Process started (PID $PID) but /health not responding yet"
            warn "Check: tail -20 $LOG"
        fi
    else
        error "Controller failed to start. Check: tail -50 $LOG"
    fi

else
    MASTER_URL=$(json_get "$INSTALL_DIR/agent_config.json" "master_url")
    LOG="$INSTALL_DIR/agent.log"
    PID_FILE="$INSTALL_DIR/agent.pid"

    if [[ -z "$MASTER_URL" || "$MASTER_URL" == *"CONTROLLER_IP"* ]]; then
        warn "master_url not configured — skipping auto-start"
        warn "Edit config:  nano $INSTALL_DIR/agent_config.json"
        warn "Then start:   cd $INSTALL_DIR && sudo ./start_agent.sh"
    else
        cd "$INSTALL_DIR"
        nohup "$DST_VENV/bin/python" -m uvicorn app.main:app \
            --host 0.0.0.0 --port 9000 \
            >> "$LOG" 2>&1 &
        echo $! > "$PID_FILE"
        sleep 3

        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            info "Agent started (PID $PID)"
        else
            error "Agent failed to start. Check: tail -50 $LOG"
        fi
    fi
fi

# =============================================================================
#  Done
# =============================================================================
banner
echo -e "${GREEN}  Install complete!${NC}"
banner
echo ""

if [[ "$MODE" == "controller" ]]; then
    echo -e "  ${CYAN}Dashboard:${NC}   http://$THIS_IP/"
    echo -e "  ${CYAN}API health:${NC}  http://$THIS_IP:8000/health"
    echo -e "  ${CYAN}Login:${NC}       any username / any password (default dev mode)"
    echo -e "  ${CYAN}Logs:${NC}        tail -f $INSTALL_DIR/logs/backend.log"
    echo ""
    echo -e "  ${YELLOW}━━ Copy this command to install agents ━━${NC}"
    echo -e "  ${YELLOW}sudo ./install.sh agent $THIS_IP $AGENT_TOKEN${NC}"
    echo ""
fi

if [[ "$MODE" == "agent" ]]; then
    MASTER_URL=$(json_get "$INSTALL_DIR/agent_config.json" "master_url")
    echo -e "  ${CYAN}Agent health:${NC} http://$THIS_IP:9000/health"
    echo -e "  ${CYAN}Controller:${NC}   $MASTER_URL"
    echo -e "  ${CYAN}Logs:${NC}         tail -f $INSTALL_DIR/agent.log"
    echo ""
    if [[ -z "$MASTER_URL" || "$MASTER_URL" == *"CONTROLLER_IP"* ]]; then
        echo -e "  ${YELLOW}⚠  Configure and start manually:${NC}"
        echo -e "     nano $INSTALL_DIR/agent_config.json"
        echo -e "     cd $INSTALL_DIR && sudo ./start_agent.sh"
    else
        echo -e "  ${CYAN}Next:${NC} Approve this node on the dashboard → Join Requests"
    fi
    echo ""
fi
