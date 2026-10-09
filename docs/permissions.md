# Staff permissions

| Action | Owner | Admin | Operator | Viewer |
|---|---|---|---|---|
| Live Chat read | yes | yes | yes | yes |
| Live Chat reply | yes | yes | yes | no |
| Requests view | yes | yes | yes | yes |
| Requests assign or status | yes | yes | yes | no |
| AI Setup edit | yes | yes | no | no |
| Billing view | yes | yes | no | no |
| Staff management | yes | yes | no | no |

The API returns 403 when a role is not allowed. Assigning a request to someone who is not an active member returns 400.
