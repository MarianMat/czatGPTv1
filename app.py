import streamlit as st
import openai
import os, json
from pathlib import Path
from datetime import datetime
from qdrant_utils import init_qdrant, save_to_qdrant, get_sessions, get_session_history, delete_session

# 🔐 Klucze API z zaawansowanych ustawień Streamlit
openai.api_key = st.secrets["OPENAI_API_KEY"]

# 🌍 Inicjalizacja Qdrant
qdrant_client = init_qdrant()
st.session_state.qdrant_client = qdrant_client

# 📂 Baza lokalna
DB_PATH = Path("db")
DB_CONV_PATH = DB_PATH / "conversations"
DB_PATH.mkdir(exist_ok=True)
DB_CONV_PATH.mkdir(exist_ok=True)

# 📊 Cennik modeli
model_pricings = {
    "gpt-4o": {"Opis": "Multimodalny – tekst, obraz, głos", "Input": 2.5, "Output": 10.0},
    "gpt-4o-mini": {"Opis": "Lekki i tani do chatbotów", "Input": 0.15, "Output": 0.6},
    "gpt-4-turbo": {"Opis": "Szybki model tekstowy", "Input": 1.5, "Output": 6.0},
    "gpt-3.5-turbo": {"Opis": "Budżetowa opcja", "Input": 0.5, "Output": 1.5}
}
USD_TO_PLN = 3.97
DEFAULT_PERSONALITY = "Jesteś pomocnym, uprzejmym i zwięzłym asystentem AI."

# 📘 Ładowanie / tworzenie konwersacji
def load_or_create_conversation():
    current_file = DB_PATH / "current.json"
    if not current_file.exists():
        convo = {
            "id": 1,
            "name": "Konwersacja 1",
            "chatbot_personality": DEFAULT_PERSONALITY,
            "messages": [],
            "model": "gpt-4o"
        }
        with open(DB_CONV_PATH / "1.json", "w") as f:
            json.dump(convo, f)
        with open(current_file, "w") as f:
            json.dump({"current_conversation_id": 1}, f)
    with open(current_file, "r") as f:
        convo_id = json.load(f)["current_conversation_id"]
    with open(DB_CONV_PATH / f"{convo_id}.json", "r") as f:
        convo = json.load(f)
    st.session_state.update(convo)

def save_conversation():
    convo = {
        "id": st.session_state["id"],
        "name": st.session_state["name"],
        "chatbot_personality": st.session_state["chatbot_personality"],
        "messages": st.session_state["messages"],
        "model": st.session_state["model"]
    }
    with open(DB_CONV_PATH / f"{convo['id']}.json", "w") as f:
        json.dump(convo, f)

def get_reply(prompt, memory, model, personality):
    messages = [{"role": "system", "content": personality}] + memory + [{"role": "user", "content": prompt}]
    response = openai.ChatCompletion.create(model=model, messages=messages)
    usage = response.usage or {}
    return {
        "role": "assistant",
        "content": response.choices[0].message.content,
        "usage": {
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens
        }
    }

# 🚀 Inicjalizacja
st.set_page_config(page_title="MarianGPT", layout="centered")
st.title("🧠 MarianGPT – Inteligentny czat z pamięcią")

if "id" not in st.session_state:
    load_or_create_conversation()

# 💬 Historia rozmowy
st.subheader(f"💬 Rozmowa: {st.session_state['name']}")
for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 🧠 Nowa wiadomość
prompt = st.chat_input("Zadaj pytanie")
if prompt:
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

    save_conversation()
    save_to_qdrant(prompt, reply["content"], f"Conv{st.session_state['id']}", st.session_state.qdrant_client)

# ⚙️ Ustawienia w sidebarze
with st.sidebar:
    st.header("⚙️ Ustawienia czatu")

    st.session_state["model"] = st.selectbox("🤖 Wybierz model GPT", options=list(model_pricings.keys()), index=list(model_pricings.keys()).index(st.session_state["model"]), on_change=save_conversation)
    model_info = model_pricings[st.session_state["model"]]
    st.markdown(f"📌 *{model_info['Opis']}*")
    st.markdown(f"- **Input**: ${model_info['Input']} / 1M tokenów\n- **Output**: ${model_info['Output']} / 1M tokenów")

    st.session_state["memory_mode"] = st.selectbox("🧠 Tryb pamięci", ["Ostatnie 10 wiadomości", "Rozszerzona (30)", "Pełna historia"])

    st.session_state["chatbot_personality"] = st.text_area("🎭 Styl GPT", value=st.session_state["chatbot_personality"], height=150, on_change=save_conversation)

    if st.button("📤 Eksportuj rozmowę"):
        chat_txt = "\n\n".join([f"{m['role'].upper()}: {m['content']}" for m in st.session_state["messages"]])
        filename = f"{st.session_state['name'].replace(' ', '_')}.txt"
        st.download_button("⬇️ Pobierz jako TXT", chat_txt, file_name=filename)

    total_cost = 0
    for msg in st.session_state["messages"]:
        if "usage" in msg:
            total_cost += msg["usage"]["prompt_tokens"] * model_info["Input"] / 1_000_000
            total_cost += msg["usage"]["completion_tokens"] * model_info["Output"] / 1_000_000

    st.metric("💰 Koszt (USD)", f"${total_cost:.4f}")
    st.metric("💰 Koszt (PLN)", f"{total_cost * USD_TO_PLN:.4f}")
