export default async function handler(req, res) {
  try {
    const response = await fetch(
      "https://web-api-prod-ytp.tcddtasimacilik.gov.tr/tms/train/train-availability?environment=dev&userId=1",
      {
        method: "POST",
        headers: {
          "Authorization": "Bearer eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJlVFFicDhDMmpiakp1cnUzQVk2a0ZnV186U29MQXZIMmJ5bTJ2OUg5THhRIn0.eyJleHAiOjE3MjEzODQ0NzAsImlhdCI6MTcyMTM4NDQxMCwianRpIjoiYWFlNjVkNzgtNmRkZS00ZGY4LWEwZWYtYjRkNzZiYjZlODNjIiwiaXNzIjoiaHR0cDovL3l0cC1wcm9kLW1hc3RlcjEudGNkZHRhc2ltYWNpbGlrLmdvdi50cjo4MDgwL3JlYWxtcy9tYXN0ZXIiLCJhdWQiOiJhY2NvdW50Iiwic3ViIjoiMDAzNDI3MmMtNTc2Yi00OTBlLWJhOTgtNTFkMzc1NWNhYjA3IiwidHlwIjoiQmVhcmVyIiwiYXpwIjoidG1zIiwic2Vzc2lvbl9zdGF0ZSI6IjAwYzM4NTJiLTg1YjEtNDMxNS04OGIwLWQ0MWMxMTcyYzA0MSIsImFjciI6IjEiLCJyZWFsbV9hY2Nlc3MiOnsicm9sZXMiOlsiZGVmYXVsdC1yb2xlcy1tYXN0ZXIiLCJvZmZsaW5lX2FjY2VzcyIsInVtYV9hdXRob3JpemF0aW9uIl19LCJyZXNvdXJjZV9hY2Nlc3MiOnsiYWNjb3VudCI6eyJyb2xlcyI6WyJtYW5hZ2UtYWNjb3VudCIsIm1hbmFnZS1hY2NvdW50LWxpbmtzIiwidmlldy1wcm9maWxlIl19fSwic2NvcGUiOiJvcGVuaWQgZW1haWwgcHJvZmlsZSIsInNpZCI6IjAwYzM4NTJiLTg1YjEtNDMxNS04OGIwLWQ0MWMxMTcyYzA0MSIsImVtYWlsX3ZlcmlmaWVkIjpmYWxzZSwicHJlZmVycmVkX3VzZXJuYW1lIjoid2ViIiwiZ2l2ZW5fbmFtZSI6IiIsImZhbWlseV9uYW1lIjoiIn0.AIW_4Qws2wfwxyVg8dgHRT9jB3qNavob2C4mEQIQGl3urzW2jALPx-e51ZwHUb-TXB-X2RPHakonxKnWG6tDIP5aKhiidzXDcr6pDDoYU5DnQhMg1kywyOaMXsjLFjuYN5PAyGUMh6YSOVsg1PzNh-5GrJF44pS47JnB9zk03Pr08napjsZPoRB-5N4GQ49cnx7ePC82Y7YIc-gTew2baqKQPz9_v381Gbm2V38PZDH9KldlcWut7kqQYJFMJ7dkM_entPJn9lFk7R5h5j_06OlQEpWRMQTn9SQ1AYxxmZxBu5XYMKDkn4rzIIVCkdTPJNCt5PvjENjClKFeUA1DOg",
          "Content-Type": "application/json",
          "Accept": "application/json"
        },
        body: JSON.stringify({
          searchRoutes: [
            {
              departureStationId: 93,
              arrivalStationId: 20,
              departureDate: "2-5-2026 21:00:00"
            }
          ],
          passengerTypeCounts: [{ id: 0, count: 1 }],
          searchReservation: false
        })
      }
    );

    const text = await response.text();

    // 🔴 Detect HTML response (your current error)
    if (text.trim().startsWith("<")) {
      return res.status(500).json({
        error: "API returned HTML instead of JSON (likely blocked or expired token)",
        status: response.status,
        preview: text.slice(0, 300)
      });
    }

    let json;
    try {
      json = JSON.parse(text);
    } catch (e) {
      return res.status(500).json({
        error: "Invalid JSON from API",
        message: e.message,
        preview: text.slice(0, 300)
      });
    }

    // 🔥 SAFE parsing
    const result = [];

    for (const block of json.trainAvailabilities || []) {
      for (const train of block.trains || []) {
        if (train.type !== "YHT") continue;

        let seats = 0;

        for (const car of train.cars || []) {
          for (const a of car.availabilities || []) {
            const name = (a.cabinClass?.name || "").toLowerCase();
            if (!name.includes("tekerlekli")) {
              seats += a.availability || 0;
            }
          }
        }

        if (seats > 0) {
          const time = new Date(train.segments[0].departureTime)
            .toLocaleTimeString("tr-TR", {
              hour: "2-digit",
              minute: "2-digit"
            });

          result.push({
            t: time,
            s: seats
          });
        }
      }
    }

    return res.status(200).json(result);
  } catch (err) {
    return res.status(500).json({
      error: "Server crashed",
      message: err.message
    });
  }
}