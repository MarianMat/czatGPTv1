import streamlit as st
import openai
import json
from pathlib import Path
from qdrant_utils import init_qdrant, save_to_qdrant

# 🔐 Inicjalizacja API
openai.api_key = st.secrets["OPENAI_API_KEY"]
qdrant_client = init_qdrant()

# 📊 Cennik modeli
model_pricings = {
    "gpt-4o":      {"Opis": "Multimodalny – tekst, obraz, głos", "Input": 2.5, "Output": 10.0},
    "gpt-4o-mini": {"Opis": "Lekki i tani do chatbotów",       "Input": 0.15, "Output": 0.6},
    "gpt-4-turbo": {"Opis": "Szybki tekstowy model",            "Input": 1.5, "Output": 6.0},
    "gpt-3.5-turbo":{"Opis": "Budżetowa opcja",                 "Input": 0.5, "Output": 1.5}
}
USD_TO_PLN = 3.97

# 🌐 Tłumaczenia interfejsu
translations = {
    "Polski": {
        "title": "🧠 MójGPT – Inteligentny czat z pamięcią",
        "chat_title": "💬 Rozmowa",
        "input_placeholder": "Zadaj pytanie",
        "language_switch": "🌍 Język interfejsu",
        "conversation_list": "📂 Wybierz rozmowę",
        "new_conversation": "🔄 Nowa rozmowa",
        "default_conversation_name": "Rozmowa {}",
        "model_select": "🤖 Wybierz model GPT",
        "personality": "🎭 Styl GPT",
        "memory_mode": "🧠 Tryb pamięci",
        "export_button": "📤 Eksportuj rozmowę",
        "download_txt": "⬇️ Pobierz jako TXT",
        "cost_usd": "💰 Koszt (USD)",
        "cost_pln": "💰 Koszt (PLN)",
        "default_personality": "Jesteś pomocnym, uprzejmym i zwięzłym asystentem AI."
    },
    "Українська": {
        "title": "🧠 MійGPT – Інтелектуальний чат з памʼяттю",
        "chat_title": "💬 Бесіда",
        "input_placeholder": "Задай запитання",
        "language_switch": "🌍 Мова інтерфейсу",
        "conversation_list": "📂 Виберіть бесіду",
        "new_conversation": "🔄 Нова бесіда",
        "default_conversation_name": "Бесіда {}",
        "model_select": "🤖 Виберіть модель GPT",
        "personality": "🎭 Стиль GPT",
        "memory_mode": "🧠 Режим памʼяті",
        "export_button": "📤 Експортувати бесіду",
        "download_txt": "⬇️ Завантажити як TXT",
        "cost_usd": "💰 Вартість (USD)",
        "cost_pln": "💰 Вартість (PLN)",
        "default_personality": "Ви корисний, ввічливий та лаконічний AI-помічник."
    }
}

# 📁 Lokalne pliki
DB_PATH      = Path("db")
DB_CONV_PATH = DB_PATH / "conversations"
DB_CONV_PATH.mkdir(parents=True, exist_ok=True)

def detect_topic(prompt: str) -> str:
    resp = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Podaj krótki temat tej rozmowy w 3–5 słowach."},
            {"role": "user", "content": prompt}
        ]
    )
    return resp.choices[0].message.content.strip()

def get_current_convo_id() -> int:
    f = DB_PATH / "current.json"
    if not f.exists():
        DB_PATH.mkdir(exist_ok=True)
        with open(f, "w") as fp:
            json.dump({"current_conversation_id": 1}, fp)
        return 1
    with open(f) as fp:
        return json.load(fp)["current_conversation_id"]

def list_conversations():
    files = DB_CONV_PATH.glob("*.json")
    convos = []
    for file in files:
        with open(file) as fp:
            c = json.load(fp)
            convos.append((c["id"], c["name"]))
    return sorted(convos, key=lambda x: x[0])

def create_new_conversation(name_template: str, default_personality: str):
    existing = list_conversations()
    new_id = max([cid for cid, _ in existing], default=0) + 1
    name = name_template.format(new_id)
    convo = {
        "id": new_id,
        "name": name,
        "chatbot_personality": default_personality,
        "messages": [],
        "model": "gpt-4o"
    }
    with open(DB_CONV_PATH / f"{new_id}.json", "w") as fp:
        json.dump(convo, fp)
    with open(DB_PATH / "current.json", "w") as fp:
        json.dump({"current_conversation_id": new_id}, fp)
    st.experimental_rerun()

def load_or_create_conversation():
    convo_id = get_current_convo_id()
    convo_file = DB_CONV_PATH / f"{convo_id}.json"
    if not convo_file.exists():
        # jeśli nie ma pliku, tworzymy
        create_new_conversation(
            translations["Polski"]["default_conversation_name"],
            translations["Polski"]["default_personality"]
        )
    with open(convo_file) as fp:
        convo = json.load(fp)
    st.session_state.update(convo)

def switch_conversation(convo_id: int):
    with open(DB_PATH / "current.json", "w") as fp:
        json.dump({"current_conversation_id": convo_id}, fp)
    st.experimental_rerun()

def save_conversation():
    convo = {
        "id": st.session_state["id"],
        "name": st.session_state["name"],
        "chatbot_personality": st.session_state["chatbot_personality"],
        "messages": st.session_state["messages"],
        "model": st.session_state["model"]
    }
    with open(DB_CONV_PATH / f"{convo['id']}.json", "w") as fp:
        json.dump(convo, fp)

def get_reply(prompt: str, memory: list, model: str, personality: str) -> dict:
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
lang = st.sidebar.selectbox(translations["Polski"]["language_switch"], ["Polski", "Українська"])
t = translations[lang]

# sidebar: Nowa rozmowa
if st.sidebar.button(t["new_conversation"]):
    create_new_conversation(t["default_conversation_name"], t["default_personality"])

# sidebar: Lista rozmów
st.sidebar.markdown(f"**{t['conversation_list']}**")
for cid, name in list_conversations():
    if st.sidebar.button(f"{name}", key=f"load_{cid}"):
        switch_conversation(cid)

# załaduj aktualną konwersację
if "id" not in st.session_state:
    load_or_create_conversation()

# 🎨 Ustawienia ogólne
st.sidebar.markdown("---")
st.sidebar.header("⚙️ " + t["model_select"])
st.session_state["model"] = st.sidebar.selectbox(
    t["model_select"],
    list(model_pricings.keys()),
    index=list(model_pricings.keys()).index(st.session_state["model"]),
    on_change=save_conversation
)
info = model_pricings[st.session_state["model"]]
st.sidebar.markdown(f"📌 *{info['Opis']}*")
st.sidebar.markdown(f"- Input: ${info['Input']} / 1M\n- Output: ${info['Output']} / 1M")

st.sidebar.markdown("---")
st.sidebar.subheader(t["memory_mode"])
st.session_state["memory_mode"] = st.sidebar.selectbox(
    t["memory_mode"],
    ["Ostatnie 10 wiadomości", "Rozszerzona (30)", "Pełna historia"]
)

st.sidebar.markdown("---")
st.sidebar.subheader(t["personality"])
st.session_state["chatbot_personality"] = st.sidebar.text_area(
    t["personality"],
    value=st.session_state["chatbot_personality"],
    height=150,
    on_change=save_conversation
)

st.sidebar.markdown("---")
if st.sidebar.button(t["export_button"]):
    chat_txt = "\n\n".join([f"{m['role'].upper()}: {m['content']}" for m in st.session_state["messages"]])
    filename = f"{st.session_state['name'].replace(' ', '_')}.txt"
    st.sidebar.download_button(t["download_txt"], chat_txt, file_name=filename)

# 🧮 Kalkulacja kosztów
usd_cost = 0.0
model_info = model_pricings[st.session_state["model"]]
for m in st.session_state["messages"]:
    if "usage" in m:
        usd_cost += m["usage"]["prompt_tokens"] * model_info["Input"] / 1_000_000
        usd_cost += m["usage"]["completion_tokens"] * model_info["Output"] / 1_000_000
st.sidebar.metric(t["cost_usd"], f"${usd_cost:.4f}")
st.sidebar.metric(t["cost_pln"], f"{usd_cost * USD_TO_PLN:.4f}")

# 🧠 Główne okno czatu
st.title(t["title"])
st.subheader(f"{t['chat_title']}: {st.session_state['name']}")

for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

prompt = st.chat_input(t["input_placeholder"])
if prompt:
    # zapisz użytkownika
    st.session_state["messages"].append({"role": "user", "content": prompt})
    # jeśli to pierwsze pytanie -> nadaj temat nazwie
    if len(st.session_state["messages"]) == 1:
        topic = detect_topic(prompt)
        st.session_state["name"] = topic[:48]
    # wybór pamięci
    mem = st.session_state["memory_mode"]
    if mem == "Ostatnie 10 wiadomości":
        memory = st.session_state["messages"][-10:]
    elif mem == "Rozszerzona (30)":
        memory = st.session_state["messages"][-30:]
    else:
        memory = st.session_state["messages"]
    # generuj odpowiedź
    reply = get_reply(prompt, memory, st.session_state["model"], st.session_state["chatbot_personality"])
    st.session_state["messages"].append(reply)
    with st.chat_message("assistant"):
        st.markdown(reply["content"])
    # zapis
    save_conversation()
    save_to_qdrant(prompt, reply["content"], f"Conv{st.session_state['id']}", qdrant_client)
