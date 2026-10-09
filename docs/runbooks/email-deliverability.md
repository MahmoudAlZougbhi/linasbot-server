# Email deliverability

Live DNS is unchanged. These records are the ones to publish at the P10 cutover, after the Resend domain is confirmed.

| Record | Value |
|---|---|
| SPF | `v=spf1 include:amazonses.com include:_spf.resend.com ~all` only if Resend's current docs still say that. Copy the exact include from the Resend domain page at cutover. |
| DKIM | The CNAME pair Resend shows for the sending domain. |
| DMARC | `v=DMARC1; p=quarantine; rua=mailto:dmarc@linasaibot.com` after a week of `p=none` monitoring. |

Bounce and complaint webhooks stay on the existing Resend webhook path. The support-address MX is a P10 item.
