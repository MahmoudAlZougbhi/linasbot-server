#!/bin/sh
# Point droplet nginx at the local app and the cluster. Weight 0 sends nothing to the cluster.
# Usage: set_cluster_weight.sh <0-100> <cluster-host:port>
set -eu
weight="${1:?weight 0-100}"
cluster="${2:?cluster host:port}"
case "$weight" in
  ''|*[!0-9]*) echo "weight must be 0-100"; exit 2 ;;
esac
if [ "$weight" -gt 100 ]; then
  echo "weight must be 0-100"
  exit 2
fi
local_weight=$((100 - weight))
if [ "$weight" -eq 0 ]; then
  cluster_line="server ${cluster} down;"
  local_line="server 127.0.0.1:8003;"
elif [ "$local_weight" -eq 0 ]; then
  cluster_line="server ${cluster};"
  local_line="server 127.0.0.1:8003 down;"
else
  cluster_line="server ${cluster} weight=${weight};"
  local_line="server 127.0.0.1:8003 weight=${local_weight};"
fi
cat > /etc/nginx/conf.d/linas-cluster-weight.conf << EOF
upstream linas_upstream {
  ${local_line}
  ${cluster_line}
  keepalive 16;
}
upstream linas_cluster_only {
  server ${cluster};
  keepalive 8;
}
map \$http_x_linas_route \$linas_backend {
  default linas_upstream;
  cluster linas_cluster_only;
}
EOF
site=/etc/nginx/sites-enabled/linasaibot
if [ -f "$site" ]; then
  python3 - "$site" << 'PY'
import pathlib, sys
path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
text = text.replace("proxy_pass http://127.0.0.1:8003;", "proxy_pass http://$linas_backend;")
needle = "proxy_set_header X-Served-By $upstream_addr;"
if needle not in text:
    text = text.replace(
        "proxy_pass http://$linas_backend;",
        "proxy_pass http://$linas_backend;\n        proxy_set_header X-Served-By $upstream_addr;",
    )
path.write_text(text, encoding="utf-8")
PY
fi
nginx -t
nginx -s reload
echo "cluster_weight=${weight}"
