import streamlit as st
import openai, json
from pathlib import Path
from qdrant_utils import init_qdrant, save_to_qdrant

openai.api_key = st.secrets["OPENAI_API_KEY"]
qdrant_client = init_qdrant()

# 📊 Cennik modeli
model_pricings = {
    "gpt-4o": {"Opis": "Multimodalny – tekst, obraz, głos", "Input": 2.5, "Output": 10.0},
    "gpt-4o-mini": {"Opis": "Lekki i tani do chatbotów", "Input": 0.15, "Output": 0.6},
    "gpt-4-turbo": {"Opis": "Szybki tekstowy model", "Input": 1.5, "Output": 6.0},
    "gpt-3.5-turbo": {"Opis": "Budżetowa opcja", "Input": 0.5, "Output": 1.5}
}
USD_TO_PLN = 3.97

translations = {
    "Polski": {
        "title": "🧠 MójGPT – Inteligentny czat z pamięcią",
        "chat_title": "💬 Rozmowa",
        "input_placeholder": "Zadaj pytanie",
        "language_switch": "🌍 Język interfejsu",
        "model_select": "🤖 Wybierz model GPT",
        "personality": "🎭 Styl GPT",
        "memory_mode": "🧠 Tryb pamięci",
        "export_button": "📤 Eksportuj rozmowę",
        "download_txt": "⬇️ Pobierz jako TXT",
        "cost_usd": "💰 Koszt (USD)",
        "cost_pln": "💰 Koszt (PLN)",
        "default_personality": "Jesteś pomocnym, uprzejmym i zwięzłym asystentem AI.",
        "convo_list": "📂 Wybierz rozmowę:"
    },
    "Українська": {
        "title": "🧠 MійGPT – Інтелектуальний чат з памʼяттю",
        "chat_title": "💬 Бесіда",
        "input_placeholder": "Задай запитання",
        "language_switch": "🌍 Мова інтерфейсу",
        "model_select": "🤖 Вибери модель GPT",
        "personality": "🎭 Стиль GPT",
        "memory_mode": "🧠 Режим памʼяті",
        "export_button": "📤 Експортувати бесіду",
        "download_txt": "⬇️ Завантажити як TXT",
        "cost_usd": "💰 Вартість (USD)",
        "cost_pln": "💰 Вартість (PLN)",
        "default_personality": "Ви корисний, ввічливий та лаконічний AI-помічник.",
        "convo_list": "📂 Виберіть бесіду:"
    }
}

# 📁 Lokalna baza
DB_PATH = Path("db")
DB_CONV_PATH = DB_PATH / "conversations"
DB_PATH.mkdir(exist_ok=True)
DB_CONV_PATH.mkdir(exist_ok=True)

def detect_topic(prompt):
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Podaj krótki temat tej rozmowy w 3–5 słowach."},
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message.content.strip()

def load_conversation(convo_id):
    with open(DB_CONV_PATH / f"{convo_id}.json") as f:
        convo = json.load(f)
    with open(DB_PATH / "current.json", "w") as f:
        json.dump({"current_conversation_id": convo_id}, f)
    st.session_state.update(convo)

def get_current_conversation_id():
    current_file = DB_PATH / "current.json"
    if not current_file.exists():
        with open(current_file, "w") as f: json.dump({"current_conversation_id": 1}, f)
        return 1
    with open(current_file) as f: return json.load(f)["current_conversation_id"]

def load_or_create_conversation():
    convo_id = get_current_conversation_id()
    convo_path = DB_CONV_PATH / f"{convo_id}.json"
    if not convo_path.exists():
        convo = {
            "id": convo_id,
            "name": f"Rozmowa {convo_id}",
            "chatbot_personality": translations["Polski"]["default_personality"],
            "messages": [],
            "model": "gpt-4o"
        }
        with open(convo_path, "w") as f: json.dump(convo, f)
    with open(convo_path) as f: convo = json.load(f)
    st.session_state.update(convo)

def save_conversation():
    convo = {
        "id": st.session_state["id"],
        "name": st.session_state["name"],
        "chatbot_personality": st.session_state["chatbot_personality"],
        "messages": st.session_state["messages"],
        "model": st.session_state["model"]
    }
    with open(DB_CONV_PATH / f"{convo['id']}.json", "w") as f: json.dump(convo, f)

def get_reply(prompt, memory, model, personality):
    msgs = [{"role": "system", "content": personality}] + memory + [{"role": "user", "content": prompt}]
    resp = openai.ChatCompletion.create(model=model, messages=msgs)
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

# 🚀 Start aplikacji
st.set_page_config(page_title="MójGPT", layout="centered")

# 🌍 Wybór języka
lang = st.sidebar.selectbox("🌍 Wybierz język", ["Polski", "Українська"])
t = translations[lang]

if "id" not in st.session_state: load_or_create_conversation()
if st.session_state.get("chatbot_personality") not in [translations["Polski"]["default_personality"], translations["Українська"]["default_personality"]]:
    st.session_state["chatbot_personality"] = t["default_personality"]

st.title(t["title"])
st.subheader(f"{t['chat_title']}: {st.session_state['name']}")

for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]): st.markdown(msg["content"])

prompt = st.chat_input(t["input_placeholder"])
if prompt:
    st.session_state["messages"].append({"role": "user", "content": prompt})
    if len(st.session_state["messages"]) == 1:
        topic = detect_topic(prompt)
        st.session_state["name"] = topic[:50]

    mode = st.session_state.get("memory_mode", "Ostatnie 10 wiadomości")
    memory = st.session_state["messages"][-10:] if mode == "Ostatnie 10 wiadomości" else \
             st.session_state["messages"][-30:] if mode == "Rozszerzona (30)" else \
             st.session_state["messages"]

    reply = get_reply(prompt, memory, st.session_state["model"], st.session_state["chatbot_personality"])
    st.session_state["messages"].append(reply)
    with st.chat_message("assistant"): st.markdown(reply["content"])
    save_conversation()
    save_to_qdrant(prompt, reply["content"], f"Conv{st.session_state['id']}", qdrant_client)

# ⚙️ Sidebar – ustawienia
st.sidebar.markdown("---")
st.sidebar.header("⚙️ " + t["model_select"])
st.session_state["model"] = st.sidebar.selectbox(t["model_select"], list(model_pricings.keys()), index=list(model_pricings.keys()).index(st.session_state["model"]), on_change=save_conversation)

info = model_pricings[st.session_state["model"]]
st.sidebar.markdown(f"📌 *{info['Opis']}*")
st.sidebar.markdown(f"- Input: ${info['Input']} / 1M\n- Output: ${info['Output']} / 
