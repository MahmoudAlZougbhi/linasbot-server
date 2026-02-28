"""Check if smart messaging routes are registered"""
from modules.core import app

print("=" * 60)
print("🔍 Checking Smart Messaging API Routes")
print("=" * 60)

smart_messaging_routes = []
for route in app.routes:
    if hasattr(route, 'path') and 'smart-messaging' in route.path:
        method = ', '.join(route.methods) if hasattr(route, 'methods') else 'N/A'
        smart_messaging_routes.append(f"{method:10} {route.path}")

if smart_messaging_routes:
    print(f"\n✅ Found {len(smart_messaging_routes)} Smart Messaging routes:\n")
    for route in sorted(smart_messaging_routes):
        print(f"   {route}")
else:
    print("\n❌ No Smart Messaging routes found!")

print("\n" + "=" * 60)

# Check specifically for send-test-template
test_template_route = any('send-test-template' in route.path for route in app.routes if hasattr(route, 'path'))
if test_template_route:
    print("✅ /api/smart-messaging/send-test-template endpoint is registered")
else:
    print("❌ /api/smart-messaging/send-test-template endpoint NOT found")

print("=" * 60)
