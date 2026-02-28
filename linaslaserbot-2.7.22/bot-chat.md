API Call: get_missed_appointments for date=2025-12-14
âœ… No missed appointments found
ًں“ٹ Statistics:

- Missed appointments found: 0
- Processed: 0
- Failed: 0
- No-show messages created: 0
- # Total in dict: 0
  âœ… Smart Messaging Scheduler started successfully
  ًں“… Scheduled jobs:
- Populate messages from appointments: Every 2 hours (+ on startup)
- Populate no-show messages from missed: Every 2 hours (+ on startup)
- Monitor messages: Every 10 minutes
- Appointment reminders: Every 30 minutes
- Missed yesterday follow-ups: Daily at 10:00 AM
- Missed this month follow-ups: 1st of month at 11:00 AM
- # Attended yesterday thank you: Daily at 9:00 PM
  INFO: Application startup complete.
  INFO: Uvicorn running on http://0.0.0.0:8003 (Press CTRL+C to quit)
  INFO: 194.246.89.131:0 - "GET /api/test HTTP/1.0" 200 OK
  INFO: 194.246.89.131:0 - "GET /api/smart-messaging/status HTTP/1.0" 200 OK
  INFO: 194.246.89.131:0 - "GET /api/smart-messaging/messages?status=all HTTP/1.0" 200 OK
  INFO: 194.246.89.131:0 - "GET /api/smart-messaging/templates HTTP/1.0" 200 OK
  âœ… Loaded 8 MontyMobile templates
  ًں“‹ Template 'same_day_checkin' expects parameters: ['customer_name', 'appointment_time']
  ًں“‹ Sending parameters: {'customer_name': 'Test Customer', 'appointment_time': '02:00 PM'}
  ًں“¤ Sending test template 'same_day_checkin' to 96176466674
  ًں”چ DEBUG build_template_payload:
  template_id: same_day_checkin (type: <class 'str'>)
  phone_number: 96176466674 (type: <class 'str'>)
  language: ar (type: <class 'str'>)
  parameters: {'customer_name': 'Test Customer', 'appointment_time': '02:00 PM'}
  Template Name: same_day_checkin
  Template WA ID: 1397546108382697
  ًں“¤ Sending template 'same_day_checkin' to 96176466674 (lang: ar)
  URL: https://omni-apis.montymobile.com/notification/api/v2/WhatsappApi/send-whatsapp
  Tenant: 98df9ffe-fa84-41ee-9293-33614722d952
  API ID: 9db12f0d-3c27-4d9c-b9fd-0227aebfd81d
  API Key: f5a24c81de876f85f0d6...
  Payload: {"to": "96176466674", "type": "template", "source": "96178974402", "template": {"name": "same_day_checkin", "language": {"code": "ar"}, "components": [{"type": "header", "parameters": []}, {"type": "b...
  Response: 200
  âœ… Template sent successfully! Message ID: 25b24c9a-aa68-4ea9-9494-14e3ed725e8f
  INFO: 194.246.89.131:0 - "POST /api/smart-messaging/send-test-template HTTP/1.0" 200 OK
  ًں“‹ Template 'reminder_24h' expects parameters: ['customer_name', 'appointment_date', 'appointment_time', 'branch_name', 'service_name']
  ًں“‹ Sending parameters: {'customer_name': 'Test Customer', 'appointment_date': '2025-12-25', 'appointment_time': '02:00 PM', 'branch_name': "Lina's Laser Center", 'service_name': 'Laser Hair Removal'}
  ًں“¤ Sending test template 'reminder_24h' to 96176466674
  ًں”چ DEBUG build_template_payload:
  template_id: reminder_24h (type: <class 'str'>)
  phone_number: 96176466674 (type: <class 'str'>)
  language: ar (type: <class 'str'>)
  parameters: {'customer_name': 'Test Customer', 'appointment_date': '2025-12-25', 'appointment_time': '02:00 PM', 'branch_name': "Lina's Laser Center", 'service_name': 'Laser Hair Removal'}
  Template Name: reminder_24h
  Template WA ID: 1553752412438998
  ًں“¤ Sending template 'reminder_24h' to 96176466674 (lang: ar)
  URL: https://omni-apis.montymobile.com/notification/api/v2/WhatsappApi/send-whatsapp
  Tenant: 98df9ffe-fa84-41ee-9293-33614722d952
  API ID: 9db12f0d-3c27-4d9c-b9fd-0227aebfd81d
  API Key: f5a24c81de876f85f0d6...
  Payload: {"to": "96176466674", "type": "template", "source": "96178974402", "template": {"name": "reminder_24h", "language": {"code": "ar"}, "components": [{"type": "header", "parameters": []}, {"type": "body"...
  Response: 200
  âœ… Template sent successfully! Message ID: 223be441-9a50-475a-86c0-0d6af8184893
  INFO: 194.246.89.131:0 - "POST /api/smart-messaging/send-test-template HTTP/1.0" 200 OK
  ًں“‹ Template 'post_session_feedback' expects parameters: ['customer_name']
  ًں“‹ Sending parameters: {'customer_name': 'Test Customer'}
  ًں“¤ Sending test template 'post_session_feedback' to 96176466674
  ًں”چ DEBUG build_template_payload:
  template_id: post_session_feedback (type: <class 'str'>)
  phone_number: 96176466674 (type: <class 'str'>)
  language: ar (type: <class 'str'>)
  parameters: {'customer_name': 'Test Customer'}
  Template Name: post_session_feedback
  Template WA ID: 885927340658052
  ًں“¤ Sending template 'post_session_feedback' to 96176466674 (lang: ar)
  URL: https://omni-apis.montymobile.com/notification/api/v2/WhatsappApi/send-whatsapp
  Tenant: 98df9ffe-fa84-41ee-9293-33614722d952
  API ID: 9db12f0d-3c27-4d9c-b9fd-0227aebfd81d
  API Key: f5a24c81de876f85f0d6...
  Payload: {"to": "96176466674", "type": "template", "source": "96178974402", "template": {"name": "post_session_feedback", "language": {"code": "ar"}, "components": [{"type": "header", "parameters": []}, {"type...
  Response: 200
  âœ… Template sent successfully! Message ID: fdd5dc59-bd30-4f49-8697-7d331a44f2c6
  INFO: 194.246.89.131:0 - "POST /api/smart-messaging/send-test-template HTTP/1.0" 200 OK

================================================================================
ًںڑ¨ WEBHOOK HIT DETECTED!
================================================================================
âڈ° Timestamp: 2025-12-20 16:36:01.059435
ًںŒگ Client IP: 185.135.130.6
ًں“چ URL Path: /webhook
ًں”§ Method: POST
ًں“‹ Headers:
host: bot.tradershubs.site
x-real-ip: 185.135.130.6
x-forwarded-for: 185.135.130.6
x-forwarded-proto: https
connection: close
content-length: 586
x-webhook-token: mah123
x-signature: JREbMNSNArD6g21YHSLuKQiPrV+KtEStr6aLwDryqyc=
traceparent: 00-c21a850b05e491ce8c63d115660bf87a-11788d0f5b1349f2-01
content-type: application/json; charset=utf-8
================================================================================
ًں“¦ Raw body received: 586 bytes

=== WEBHOOK DATA PARSED ===
ًں“ٹ Current provider: montymobile
ًں“„ Webhook JSON data:
{
"entry": [
{
"id": "859562923476499",
"changes": [
{
"field": "messages",
"value": {
"metadata": {
"phone_number_id": "901137269746618",
"display_phone_number": "96178974402"
},
"statuses": [
{
"id": "wamid.HBgLOTYxNzY0NjY2NzQVAgARGBIxQUE0NzM1RkE1MTVBMzFFRkMA",
"status": "delivered",
"pricing": {
"billable": true,
"category": "marketing",
"pricing_model": "PMP"
},
"timestamp": "1766244956",
"conversation": {
"id": "3a0281dd04af01126c146efdc170b389",
"origin": {
"type": "marketing"
}
},
"recipient_id": "96176466674"
}
],
"messaging_product": "whatsapp"
}
}
]
}
],
"object": "whatsapp_business_account"
}
================================================================================
Using adapter: MontyMobileAdapter

================================================================================
ًں”” WEBHOOK RECEIVED - MontyMobile
================================================================================
ًں“¥ Raw webhook data:
{
"entry": [
{
"id": "859562923476499",
"changes": [
{
"field": "messages",
"value": {
"metadata": {
"phone_number_id": "901137269746618",
"display_phone_number": "96178974402"
},
"statuses": [
{
"id": "wamid.HBgLOTYxNzY0NjY2NzQVAgARGBIxQUE0NzM1RkE1MTVBMzFFRkMA",
"status": "delivered",
"pricing": {
"billable": true,
"category": "marketing",
"pricing_model": "PMP"
},
"timestamp": "1766244956",
"conversation": {
"id": "3a0281dd04af01126c146efdc170b389",
"origin": {
"type": "marketing"
}
},
"recipient_id": "96176466674"
}
],
"messaging_product": "whatsapp"
}
}
]
}
],
"object": "whatsapp_business_account"
}
================================================================================

âœ… Detected Meta/WhatsApp format from MontyMobile
ًں“¥ Parsing Meta format webhook...
âڑ ï¸ڈ Ignoring status update webhook (not a user message)
Parsed message result: None
Trying Meta fallback parser...
ERROR: Could not parse webhook from any provider
INFO: 185.135.130.6:0 - "POST /webhook HTTP/1.0" 200 OK

================================================================================
ًںڑ¨ WEBHOOK HIT DETECTED!
================================================================================
âڈ° Timestamp: 2025-12-20 16:36:01.110394
ًںŒگ Client IP: 185.135.130.6
ًں“چ URL Path: /webhook
ًں”§ Method: POST
ًں“‹ Headers:
host: bot.tradershubs.site
x-real-ip: 185.135.130.6
x-forwarded-for: 185.135.130.6
x-forwarded-proto: https
connection: close
content-length: 581
x-webhook-token: mah123
x-signature: /GoKCZNjGMVACVkHnVvz+EsD6o5gPzcZ6OR0X4ANXUw=
traceparent: 00-f07fed4cda9a9436c12fde142790033d-8924f2f72e785c6a-01
content-type: application/json; charset=utf-8
================================================================================
ًں“¦ Raw body received: 581 bytes

=== WEBHOOK DATA PARSED ===
ًں“ٹ Current provider: montymobile
ًں“„ Webhook JSON data:
{
"entry": [
{
"id": "859562923476499",
"changes": [
{
"field": "messages",
"value": {
"metadata": {
"phone_number_id": "901137269746618",
"display_phone_number": "96178974402"
},
"statuses": [
{
"id": "wamid.HBgLOTYxNzY0NjY2NzQVAgARGBIxQUE0NzM1RkE1MTVBMzFFRkMA",
"status": "sent",
"pricing": {
"billable": true,
"category": "marketing",
"pricing_model": "PMP"
},
"timestamp": "1766244955",
"conversation": {
"id": "3a0281dd04af01126c146efdc170b389",
"origin": {
"type": "marketing"
}
},
"recipient_id": "96176466674"
}
],
"messaging_product": "whatsapp"
}
}
]
}
],
"object": "whatsapp_business_account"
}
================================================================================
Using adapter: MontyMobileAdapter

================================================================================
ًں”” WEBHOOK RECEIVED - MontyMobile
================================================================================
ًں“¥ Raw webhook data:
{
"entry": [
{
"id": "859562923476499",
"changes": [
{
"field": "messages",
"value": {
"metadata": {
"phone_number_id": "901137269746618",
"display_phone_number": "96178974402"
},
"statuses": [
{
"id": "wamid.HBgLOTYxNzY0NjY2NzQVAgARGBIxQUE0NzM1RkE1MTVBMzFFRkMA",
"status": "sent",
"pricing": {
"billable": true,
"category": "marketing",
"pricing_model": "PMP"
},
"timestamp": "1766244955",
"conversation": {
"id": "3a0281dd04af01126c146efdc170b389",
"origin": {
"type": "marketing"
}
},
"recipient_id": "96176466674"
}
],
"messaging_product": "whatsapp"
}
}
]
}
],
"object": "whatsapp_business_account"
}
================================================================================

âœ… Detected Meta/WhatsApp format from MontyMobile
ًں“¥ Parsing Meta format webhook...
âڑ ï¸ڈ Ignoring status update webhook (not a user message)
Parsed message result: None
Trying Meta fallback parser...
ERROR: Could not parse webhook from any provider
INFO: 185.135.130.6:0 - "POST /webhook HTTP/1.0" 200 OK

================================================================================
ًںڑ¨ WEBHOOK HIT DETECTED!
================================================================================
âڈ° Timestamp: 2025-12-20 16:36:01.153935
ًںŒگ Client IP: 185.135.130.6
ًں“چ URL Path: /webhook
ًں”§ Method: POST
ًں“‹ Headers:
host: bot.tradershubs.site
x-real-ip: 185.135.130.6
x-forwarded-for: 185.135.130.6
x-forwarded-proto: https
connection: close
content-length: 582
x-webhook-token: mah123
x-signature: W0rt+JoBG/nXGpnzUDj9mxixZFjXqt2ktoxdpZ7gPfY=
traceparent: 00-ef2fea7ddc4631ab7535299cf48d8732-a4ccf7d4ef55283e-01
content-type: application/json; charset=utf-8
================================================================================
ًں“¦ Raw body received: 582 bytes

=== WEBHOOK DATA PARSED ===
ًں“ٹ Current provider: montymobile
ًں“„ Webhook JSON data:
{
"entry": [
{
"id": "859562923476499",
"changes": [
{
"field": "messages",
"value": {
"metadata": {
"phone_number_id": "901137269746618",
"display_phone_number": "96178974402"
},
"statuses": [
{
"id": "wamid.HBgLOTYxNzY0NjY2NzQVAgARGBJGMjZEOTYwRTM4RjM5RTlFNUUA",
"status": "delivered",
"pricing": {
"billable": true,
"category": "utility",
"pricing_model": "PMP"
},
"timestamp": "1766244946",
"conversation": {
"id": "8870999c8c106a440aa72e5307460b6d",
"origin": {
"type": "utility"
}
},
"recipient_id": "96176466674"
}
],
"messaging_product": "whatsapp"
}
}
]
}
],
"object": "whatsapp_business_account"
}
================================================================================
Using adapter: MontyMobileAdapter

================================================================================
ًں”” WEBHOOK RECEIVED - MontyMobile
================================================================================
ًں“¥ Raw webhook data:
{
"entry": [
{
"id": "859562923476499",
"changes": [
{
"field": "messages",
"value": {
"metadata": {
"phone_number_id": "901137269746618",
"display_phone_number": "96178974402"
},
"statuses": [
{
"id": "wamid.HBgLOTYxNzY0NjY2NzQVAgARGBJGMjZEOTYwRTM4RjM5RTlFNUUA",
"status": "delivered",
"pricing": {
"billable": true,
"category": "utility",
"pricing_model": "PMP"
},
"timestamp": "1766244946",
"conversation": {
"id": "8870999c8c106a440aa72e5307460b6d",
"origin": {
"type": "utility"
}
},
"recipient_id": "96176466674"
}
],
"messaging_product": "whatsapp"
}
}
]
}
],
"object": "whatsapp_business_account"
}
================================================================================

âœ… Detected Meta/WhatsApp format from MontyMobile
ًں“¥ Parsing Meta format webhook...
âڑ ï¸ڈ Ignoring status update webhook (not a user message)
Parsed message result: None
Trying Meta fallback parser...
ERROR: Could not parse webhook from any provider
INFO: 185.135.130.6:0 - "POST /webhook HTTP/1.0" 200 OK

================================================================================
ًںڑ¨ WEBHOOK HIT DETECTED!
================================================================================
âڈ° Timestamp: 2025-12-20 16:36:01.203682
ًںŒگ Client IP: 185.135.130.6
ًں“چ URL Path: /webhook
ًں”§ Method: POST
ًں“‹ Headers:
host: bot.tradershubs.site
x-real-ip: 185.135.130.6
x-forwarded-for: 185.135.130.6
x-forwarded-proto: https
connection: close
content-length: 577
x-webhook-token: mah123
x-signature: fwMi4UhTT63FE9G7GQl/MDZg38MeMXbVL8NRhxwfiVM=
traceparent: 00-a7af9a29fd3b5de591747a01357040e3-ab222e8dd8aaf449-01
content-type: application/json; charset=utf-8
================================================================================
ًں“¦ Raw body received: 577 bytes

=== WEBHOOK DATA PARSED ===
ًں“ٹ Current provider: montymobile
ًں“„ Webhook JSON data:
{
"entry": [
{
"id": "859562923476499",
"changes": [
{
"field": "messages",
"value": {
"metadata": {
"phone_number_id": "901137269746618",
"display_phone_number": "96178974402"
},
"statuses": [
{
"id": "wamid.HBgLOTYxNzY0NjY2NzQVAgARGBJGMjZEOTYwRTM4RjM5RTlFNUUA",
"status": "sent",
"pricing": {
"billable": true,
"category": "utility",
"pricing_model": "PMP"
},
"timestamp": "1766244945",
"conversation": {
"id": "8870999c8c106a440aa72e5307460b6d",
"origin": {
"type": "utility"
}
},
"recipient_id": "96176466674"
}
],
"messaging_product": "whatsapp"
}
}
]
}
],
"object": "whatsapp_business_account"
}
================================================================================
Using adapter: MontyMobileAdapter

================================================================================
ًں”” WEBHOOK RECEIVED - MontyMobile
================================================================================
ًں“¥ Raw webhook data:
{
"entry": [
{
"id": "859562923476499",
"changes": [
{
"field": "messages",
"value": {
"metadata": {
"phone_number_id": "901137269746618",
"display_phone_number": "96178974402"
},
"statuses": [
{
"id": "wamid.HBgLOTYxNzY0NjY2NzQVAgARGBJGMjZEOTYwRTM4RjM5RTlFNUUA",
"status": "sent",
"pricing": {
"billable": true,
"category": "utility",
"pricing_model": "PMP"
},
"timestamp": "1766244945",
"conversation": {
"id": "8870999c8c106a440aa72e5307460b6d",
"origin": {
"type": "utility"
}
},
"recipient_id": "96176466674"
}
],
"messaging_product": "whatsapp"
}
}
]
}
],
"object": "whatsapp_business_account"
}
================================================================================

âœ… Detected Meta/WhatsApp format from MontyMobile
ًں“¥ Parsing Meta format webhook...
âڑ ï¸ڈ Ignoring status update webhook (not a user message)
Parsed message result: None
Trying Meta fallback parser...
ERROR: Could not parse webhook from any provider
INFO: 185.135.130.6:0 - "POST /webhook HTTP/1.0" 200 OK

================================================================================
ًںڑ¨ WEBHOOK HIT DETECTED!
================================================================================
âڈ° Timestamp: 2025-12-20 16:36:01.245215
ًںŒگ Client IP: 185.135.130.6
ًں“چ URL Path: /webhook
ًں”§ Method: POST
ًں“‹ Headers:
host: bot.tradershubs.site
x-real-ip: 185.135.130.6
x-forwarded-for: 185.135.130.6
x-forwarded-proto: https
connection: close
content-length: 582
x-webhook-token: mah123
x-signature: YNopMlRHAkJWeaNZUawzHvQv9f27vM2Qud3jXWRfYXo=
traceparent: 00-157f6fd2a1706a4134038f71c03fb3a2-cf49feceb7e65a1c-01
content-type: application/json; charset=utf-8
================================================================================
ًں“¦ Raw body received: 582 bytes

=== WEBHOOK DATA PARSED ===
ًں“ٹ Current provider: montymobile
ًں“„ Webhook JSON data:
{
"entry": [
{
"id": "859562923476499",
"changes": [
{
"field": "messages",
"value": {
"metadata": {
"phone_number_id": "901137269746618",
"display_phone_number": "96178974402"
},
"statuses": [
{
"id": "wamid.HBgLOTYxNzY0NjY2NzQVAgARGBJDRkEyNzY4MUEzQUQ2RDkxMzgA",
"status": "delivered",
"pricing": {
"billable": true,
"category": "utility",
"pricing_model": "PMP"
},
"timestamp": "1766244931",
"conversation": {
"id": "fd398feb8df7d0e29d5e77a94b4bbe28",
"origin": {
"type": "utility"
}
},
"recipient_id": "96176466674"
}
],
"messaging_product": "whatsapp"
}
}
]
}
],
"object": "whatsapp_business_account"
}
================================================================================
Using adapter: MontyMobileAdapter

================================================================================
ًں”” WEBHOOK RECEIVED - MontyMobile
================================================================================
ًں“¥ Raw webhook data:
{
"entry": [
{
"id": "859562923476499",
"changes": [
{
"field": "messages",
"value": {
"metadata": {
"phone_number_id": "901137269746618",
"display_phone_number": "96178974402"
},
"statuses": [
{
"id": "wamid.HBgLOTYxNzY0NjY2NzQVAgARGBJDRkEyNzY4MUEzQUQ2RDkxMzgA",
"status": "delivered",
"pricing": {
"billable": true,
"category": "utility",
"pricing_model": "PMP"
},
"timestamp": "1766244931",
"conversation": {
"id": "fd398feb8df7d0e29d5e77a94b4bbe28",
"origin": {
"type": "utility"
}
},
"recipient_id": "96176466674"
}
],
"messaging_product": "whatsapp"
}
}
]
}
],
"object": "whatsapp_business_account"
}
================================================================================

âœ… Detected Meta/WhatsApp format from MontyMobile
ًں“¥ Parsing Meta format webhook...
âڑ ï¸ڈ Ignoring status update webhook (not a user message)
Parsed message result: None
Trying Meta fallback parser...
ERROR: Could not parse webhook from any provider
INFO: 185.135.130.6:0 - "POST /webhook HTTP/1.0" 200 OK

================================================================================
ًںڑ¨ WEBHOOK HIT DETECTED!
================================================================================
âڈ° Timestamp: 2025-12-20 16:36:01.290903
ًںŒگ Client IP: 185.135.130.6
ًں“چ URL Path: /webhook
ًں”§ Method: POST
ًں“‹ Headers:
host: bot.tradershubs.site
x-real-ip: 185.135.130.6
x-forwarded-for: 185.135.130.6
x-forwarded-proto: https
connection: close
content-length: 577
x-webhook-token: mah123
x-signature: spvO7mOyEklLKFc2W64oYke6+ZUmvLgfzSN3tLh6Oo0=
traceparent: 00-3b75b07932c0f0226614e60f170dfcbb-d1c3bb65327c08dc-01
content-type: application/json; charset=utf-8
================================================================================
ًں“¦ Raw body received: 577 bytes

=== WEBHOOK DATA PARSED ===
ًں“ٹ Current provider: montymobile
ًں“„ Webhook JSON data:
{
"entry": [
{
"id": "859562923476499",
"changes": [
{
"field": "messages",
"value": {
"metadata": {
"phone_number_id": "901137269746618",
"display_phone_number": "96178974402"
},
"statuses": [
{
"id": "wamid.HBgLOTYxNzY0NjY2NzQVAgARGBJDRkEyNzY4MUEzQUQ2RDkxMzgA",
"status": "sent",
"pricing": {
"billable": true,
"category": "utility",
"pricing_model": "PMP"
},
"timestamp": "1766244930",
"conversation": {
"id": "fd398feb8df7d0e29d5e77a94b4bbe28",
"origin": {
"type": "utility"
}
},
"recipient_id": "96176466674"
}
],
"messaging_product": "whatsapp"
}
}
]
}
],
"object": "whatsapp_business_account"
}
================================================================================
Using adapter: MontyMobileAdapter

================================================================================
ًں”” WEBHOOK RECEIVED - MontyMobile
================================================================================
ًں“¥ Raw webhook data:
{
"entry": [
{
"id": "859562923476499",
"changes": [
{
"field": "messages",
"value": {
"metadata": {
"phone_number_id": "901137269746618",
"display_phone_number": "96178974402"
},
"statuses": [
{
"id": "wamid.HBgLOTYxNzY0NjY2NzQVAgARGBJDRkEyNzY4MUEzQUQ2RDkxMzgA",
"status": "sent",
"pricing": {
"billable": true,
"category": "utility",
"pricing_model": "PMP"
},
"timestamp": "1766244930",
"conversation": {
"id": "fd398feb8df7d0e29d5e77a94b4bbe28",
"origin": {
"type": "utility"
}
},
"recipient_id": "96176466674"
}
],
"messaging_product": "whatsapp"
}
}
]
}
],
"object": "whatsapp_business_account"
}
================================================================================

âœ… Detected Meta/WhatsApp format from MontyMobile
ًں“¥ Parsing Meta format webhook...
âڑ ï¸ڈ Ignoring status update webhook (not a user message)
Parsed message result: None
Trying Meta fallback parser...
ERROR: Could not parse webhook from any provider
INFO: 185.135.130.6:0 - "POST /webhook HTTP/1.0" 200 OK
ًں“‹ Template 'no_show_followup' expects parameters: ['customer_name', 'phone_number']
ًں“‹ Sending parameters: {'customer_name': 'Test Customer', 'phone_number': '+961 1 234 567'}
ًں“¤ Sending test template 'no_show_followup' to 96176466674
ًں”چ DEBUG build_template_payload:
template_id: no_show_followup (type: <class 'str'>)
phone_number: 96176466674 (type: <class 'str'>)
language: ar (type: <class 'str'>)
parameters: {'customer_name': 'Test Customer', 'phone_number': '+961 1 234 567'}
Template Name: no_show_followup
Template WA ID: 1396511885155373
ًں“¤ Sending template 'no_show_followup' to 96176466674 (lang: ar)
URL: https://omni-apis.montymobile.com/notification/api/v2/WhatsappApi/send-whatsapp
Tenant: 98df9ffe-fa84-41ee-9293-33614722d952
API ID: 9db12f0d-3c27-4d9c-b9fd-0227aebfd81d
API Key: f5a24c81de876f85f0d6...
Payload: {"to": "96176466674", "type": "template", "source": "96178974402", "template": {"name": "no_show_followup", "language": {"code": "ar"}, "components": [{"type": "header", "parameters": []}, {"type": "b...
Response: 500
â‌Œ HTTP Error 500: {"message":"Number of body variables is invalid","code":"8_23_500","success":false,"data":null,"version":"2"}
INFO: 194.246.89.131:0 - "POST /api/smart-messaging/send-test-template HTTP/1.0" 200 OK
