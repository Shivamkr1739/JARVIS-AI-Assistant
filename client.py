import requests

url = "https://api.groq.com/openai/v1/chat/completions"
headers = {"Authorization": "Bearer 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"}
data = {
    "model": "llama3-8b-8192",
    "messages": [
        {"role": "system", "content": "You are Jarvis, a helpful AI assistant."},
        {"role": "user", "content": "Who is hrithik roshan"}
    ]
}

response = requests.post(url, headers=headers, json=data)
print(response.json()["choices"][0]["message"]["content"])
