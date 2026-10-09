# QA log access

## Droplets, until they are decommissioned

User `qa-readonly` on both production nodes. Key login only. No password. No sudo. Groups `adm` and `systemd-journal`.

```bash
journalctl -u linasbot.service -n 50 --no-pager
journalctl -u 'linasbot-worker@*' -n 50 --no-pager
journalctl -u nginx.service -n 50 --no-pager
tail -n 50 /var/log/nginx/error.log
```

On node 01 only:

```bash
journalctl -u postgresql@17-main.service -n 20 --no-pager
```

Postgres on that node is stopped. There is no Docker. There is no local Redis unit.

## Central logs

A Grafana or Better Stack user named `qa-readonly` should be Viewer on the Linas logs, metrics, and traces only. Share the password through the secrets manager, not in chat. That account is not created yet because no Grafana Cloud token is configured here.

Example queries once logs are JSON:

- `{app="linas"} | json | tenant_id="linas"`
- `{app="linas"} | json | request_id="<id>"`
- `{app="linas"} | json | status >= 500`
