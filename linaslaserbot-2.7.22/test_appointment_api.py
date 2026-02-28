import asyncio
import httpx
import api_config
import json

async def test_api():
    api_client = httpx.AsyncClient(base_url=api_config.LINASLASER_API_BASE_URL)
    headers = {
        "Authorization": f"Bearer {api_config.LINASLASER_API_TOKEN}",
        "Content-Type": "application/json"
    }

    try:
        response = await api_client.get("appointments/reminders", params={"date": "2026-01-14"}, headers=headers)
        print(f"Status Code: {response.status_code}")
        print(f"\n📦 Full Response:")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))

        data = response.json()
        if data.get("success") and "data" in data:
            api_data = data["data"]
            print(f"\n🔍 Data Structure:")
            print(f"   Type: {type(api_data)}")
            if isinstance(api_data, dict):
                print(f"   Keys: {list(api_data.keys())}")
                if "appointments" in api_data and api_data["appointments"]:
                    print(f"\n✅ First Appointment:")
                    print(json.dumps(api_data["appointments"][0], indent=2, ensure_ascii=False))
            elif isinstance(api_data, list) and api_data:
                print(f"   List length: {len(api_data)}")
                print(f"\n✅ First Item:")
                print(json.dumps(api_data[0], indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await api_client.aclose()

if __name__ == "__main__":
    asyncio.run(test_api())
