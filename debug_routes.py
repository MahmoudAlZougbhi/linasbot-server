"""Debug route registration"""
from modules.core import app

print("Before importing smart_messaging_api:")
print(f"Total routes: {len(app.routes)}")

import modules.smart_messaging_api

print("\nAfter importing smart_messaging_api:")
print(f"Total routes: {len(app.routes)}")

print("\nAll routes:")
for route in app.routes:
    if hasattr(route, 'path'):
        methods = ', '.join(route.methods) if hasattr(route, 'methods') else 'N/A'
        print(f"  {methods:15} {route.path}")
