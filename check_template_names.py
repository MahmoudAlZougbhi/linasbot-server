"""
Quick script to test different template names with MontyMobile
"""
import asyncio
import httpx
import json

API_CONFIG = {
    "base_url": "https://omni-apis.montymobile.com",
    "endpoint": "/notification/api/v2/WhatsappApi/send-whatsapp",
    "tenant": "98df9ffe-fa84-41ee-9293-33614722d952",
    "api_key": "8bd7edb95cdd5a9ab70162ada74cd5138837499063f18fac2b99004dbc752088",
    "api_id": "9db12f0d-3c27-4d9c-b9fd-0227aebfd81d",
    "source": "96178974402"
}

# Template names to test
TEMPLATE_NAMES_TO_TEST = [
    "reminder_24h",
    "reminder1",
    "reminder",
    "24h_reminder",
    "appointment_reminder",
]

async def test_template_name(template_name, phone_number):
    """Test if a template name works"""
    url = API_CONFIG["base_url"] + API_CONFIG["endpoint"]
    
    headers = {
        "Tenant": API_CONFIG["tenant"],
        "api-key": API_CONFIG["api_key"],
        "Content-Type": "application/json"
    }
    
    payload = {
        "to": phone_number,
        "type": "template",
        "source": API_CONFIG["source"],
        "template": {
            "name": template_name,
            "language": {
                "code": "ar"
            },
            "components": []
        },
        "apiId": API_CONFIG["api_id"]
    }
    
    print(f"\n🔍 Testing template: '{template_name}'")
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    if data.get("success"):
                        print(f"   ✅ SUCCESS! Template '{template_name}' works!")
                        return True, template_name
                    else:
                        print(f"   ❌ Failed: {data.get('message', 'Unknown error')}")
                except:
                    pass
            elif response.status_code == 401:
                print(f"   ⚠️  401 Unauthorized - Template might not exist or not approved")
            elif response.status_code == 404:
                print(f"   ❌ 404 Not Found - Template doesn't exist")
            else:
                print(f"   ❌ Error: {response.text[:100]}")
                
    except Exception as e:
        print(f"   ❌ Exception: {e}")
    
    return False, None

async def main():
    print("=" * 60)
    print("🧪 MONTYMOBILE TEMPLATE NAME TESTER")
    print("=" * 60)
    
    phone = input("\nEnter your phone number (e.g., 96176466674): ").strip()
    
    if not phone:
        phone = "96176466674"  # Default
    
    print(f"\n📱 Testing with phone: {phone}")
    print(f"🔑 API ID: {API_CONFIG['api_id']}")
    print(f"🌐 Tenant: {API_CONFIG['tenant']}")
    
    print(f"\n🔄 Testing {len(TEMPLATE_NAMES_TO_TEST)} template names...")
    
    working_templates = []
    
    for template_name in TEMPLATE_NAMES_TO_TEST:
        success, name = await test_template_name(template_name, phone)
        if success:
            working_templates.append(name)
        await asyncio.sleep(1)  # Wait 1 second between tests
    
    print("\n" + "=" * 60)
    print("📊 RESULTS")
    print("=" * 60)
    
    if working_templates:
        print(f"\n✅ Found {len(working_templates)} working template(s):")
        for name in working_templates:
            print(f"   - {name}")
    else:
        print("\n❌ No working templates found!")
        print("\n💡 Suggestions:")
        print("   1. Check MontyMobile portal for exact template names")
        print("   2. Verify templates are APPROVED by WhatsApp")
        print("   3. Make sure template names match exactly (case-sensitive)")
        print("   4. Try adding custom template names to test above")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
