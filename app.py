import streamlit as st
import openai, os, json, hashlib
from pathlib import Path
from dotenv import dotenv_values
from datetime import datetime
from qdrant_utils import init_qdrant, save_to_qdrant, get_sessions, get_session_history, delete_session

# ⚙️ Konfiguracja
env = dotenv_values(".env")
openai.api_key = env["OPENAI_API_KEY"]

model_pricings = {
    "gpt-4o": {"Opis": "Multimodalny – tekst, obraz, głos", "Input": 2.5, "Output": 10.0},
    "gpt-4o-mini": {"Opis": "Lekki i tani do chatbotów", "Input": 0.15, "Output": 0.6},
    "gpt-4-turbo": {"Opis": "Szybki model tekstowy", "Input": 1.5, "Output": 6.0},
    "gpt-3.5-turbo": {"Opis": "Budżetowa opcja, szybka", "Input": 0.5, "Output": 1.5},
}
USD_TO_PLN = 3.97

# 🧠 Osobowość domyślna
DEFAULT_PERSONALITY = "Jesteś pomocnym, zwięzłym i uprzejmym asystentem AI."

# 📂 Lokalna baza
DB_PATH = Path("db")
DB_CONV_PATH = DB_PATH / "conversations"
DB_PATH.mkdir(exist_ok=True)
DB_CONV_PATH.mkdir(exist_ok=True)

# 📘 Pomocnicze funkcje lokalne
def load_current_conversation():
    current_file = DB_PATH / "current.json"
    if not current_file.exists():
        convo = {
            "id": 1,
            "name": "Konwersacja 1",
            "chatbot_personality": DEFAULT_PERSONALITY,
            "messages": [],
            "model": "gpt-4o"
        }
        with open(DB_CONV_PATH / "1.json", "w") as f: f.write(json.dumps(convo))
        with open(current_file, "w") as f: f.write(json.dumps({"current_conversation_id": 1}))
    else:
        with open(current_file, "r") as f:
            convo_id = json.loads(f.read())["current_conversation_id"]
        with open(DB_CONV_PATH / f"{convo_id}.json", "r") as f:
            convo = json.loads(f.read())
    st.session_state.update({
        "id": convo["id"],
        "name": convo["name"],
        "messages": convo["messages"],
        "chatbot_personality": convo["chatbot_personality"],
        "model": convo["model"]
    })

def save_conversation():
    convo = {
        "id": st.session_state["id"],
        "name": st.session_state["name"],
        "chatbot_personality": st.session_state["chatbot_personality"],
        "messages": st.session_state["messages"],
        "model": st.session_state["model"]
    }
    with open(DB_CONV_PATH / f"{convo['id']}.json", "w") as f:
        f.write(json.dumps(convo))

# 💬 Generacja odpowiedzi
def get_reply(prompt, memory, model_name, personality):
    messages = [{"role": "system", "content": personality}] + memory + [{"role": "user", "content": prompt}]
    resp = openai.ChatCompletion.create(model=model_name, messages=messages)
    usage = resp.usage or {}
    return {
        "role": "assistant",
        "content": resp.choices[0].message.content,
        "usage": {
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens
        }
    }
# 🚀 Inicjalizacja aplikacji
st.set_page_config(page_title="MarianGPT", layout="centered")
st.title("🧠 MarianGPT – Inteligentny czat z pamięcią")

if "id" not in st.session_state:
    load_current_conversation()

if "qdrant_client" not in st.session_state:
    st.session_state.qdrant_client = init_qdrant()

client = st.session_state.qdrant_client

# 💬 Wyświetlenie historii
st.subheader(f"Rozmowa: {st.session_state['name']}")
for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 💡 Input
prompt = st.chat_input("Zadaj pytanie")
if prompt:
    with st.chat_message("user"):
        st.markdown(prompt)

    st.session_state["messages"].append({"role": "user", "content": prompt})

    memory_mode = st.session_state.get("memory_mode", "Ostatnie 10 wiadomości")
    if memory_mode == "Rozszerzona (30)":
        memory = st.session_state["messages"][-30:]
    elif memory_mode == "Pełna historia":
        memory = st.session_state["messages"]
    else:
        memory = st.session_state["messages"][-10:]

    reply = get_reply(prompt, memory, st.session_state["model"], st.session_state["chatbot_personality"])

    st.session_state["messages"].append(reply)

    with st.chat_message("assistant"):
        st.markdown(reply["content"])

    # 💾 Zapis do lokalnej bazy
    save_conversation()

    # 💾 Zapis do Qdrant
    save_to_qdrant(prompt, reply["content"], f"Conv{st.session_state['id']}", client)

# 🧪 Sidebar
with st.sidebar:
    st.header("⚙️ Ustawienia")

    # Model GPT
    st.session_state["model"] = st.selectbox(
        "🤖 Model GPT",
        options=list(model_pricings.keys()),
        index=list(model_pricings.keys()).index(st.session_state["model"]),
        on_change=save_conversation
    )
    model_info = model_pricings[st.session_state["model"]]
    st.markdown(f"📌 *{model_info['Opis']}*")
    st.markdown(f"""
**💸 Koszty za 1M tokenów**
- Input: ${model_info['Input']}
- Output: ${model_info['Output']}
""")

    # Tryb pamięci
    st.session_state["memory_mode"] = st.selectbox(
        "🧠 Pamięć czatu",
        options=["Ostatnie 10 wiadomości", "Rozszerzona (30)", "Pełna historia"]
    )

    # Osobowość
    st.session_state["chatbot_personality"] = st.text_area(
        "🎭 Styl GPT",
        value=st.session_state["chatbot_personality"],
        height=150,
        on_change=save_conversation
    )

    # Eksport rozmowy jako TXT
    if st.button("📤 Eksportuj rozmowę"):
        chat_txt = "\n\n".join([f"{m['role'].upper()}: {m['content']}" for m in st.session_state["messages"]])
        filename = f"{st.session_state['name'].replace(' ', '_')}.txt"
        st.download_button("⬇️ Pobierz jako TXT", chat_txt, file_name=filename)

    # 💰 Kalkulacja kosztów
    usd_cost = 0
    for m in st.session_state["messages"]:
        if "usage" in m:
            usd_cost += m["usage"]["prompt_tokens"] * model_info["Input"] / 1_000_000
            usd_cost += m["usage"]["completion_tokens"] * model_info["Output"] / 1_000_000
    st.metric("Koszt (USD)", f"${usd_cost:.4f}")
    st.metric("Koszt (PLN)", f"{usd_cost * USD_TO_PLN:.4f}")
