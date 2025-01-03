'''
Main entry file for the streamlit app
'''
from io import BytesIO
from groq import Groq
import streamlit as st
from styles import button_css, selectbox_css, file_uploader_css, header_container_css, transcript_container
from audiorecorder import audiorecorder
from streamlit_extras.stylable_container import stylable_container
from utils import read_from_url, prerecorded, chat_stream, create_vectorstore, read_from_youtube
from config import GROQ_CLIENT, VECTOR_INDEX

VECTOR_INDEX = VECTOR_INDEX

st.set_page_config(
    page_title="Video and Audio QA",
    layout='centered',
    page_icon='static/favicon.ico',
    menu_items={
        'About': "## Video and audio transcription, and question answering."
    }
)

groqClient = Groq()
header_container = stylable_container(
    key="header",
    css_styles=header_container_css
)
header_container.header("Video/Audio QnA", anchor=False)


ASR_MODELS = {"Whisper V3 large": "whisper-large-v3"}

GROQ_MODELS = {model.id.replace("-", " ").title() : model.id for model in Groq().models.list().data if not (model.id.startswith("whisper") or model.id.startswith("llama-guard"))}

LANGUAGES = {
    "Automatic Language Detection": None,
}


st.caption("Video and audio transcription, and question answering.")


# Dropdowns with styling
dropdown_container = stylable_container(
    key="dropdown_container",
    css_styles=selectbox_css
)

# only 1 Column for horizontal layout
col1 = st.columns(1)[0]


language = "Automatic Language Detection"
lang_options = {
    "detect_language" if language == "Automatic Language Detection" else "language": True if language == "Automatic Language Detection" else LANGUAGES[language]
}

asr_model = "Whisper V3 large"

with col1:
    groq_model = st.selectbox("Supported LLMs", options=list(GROQ_MODELS.keys()))

audio_source = st.radio(
    "Choose audio source",
    # options=["Record audio", "Upload media file", "Load media from URL"],
    options=["Upload media file", "Load media from URL"],
    horizontal=True,
)

if audio_source == "Upload media file":
    file_uploader = stylable_container(
    key="file_uploader",
    css_styles=file_uploader_css
    )
    audio_file = file_uploader.file_uploader(
        label="Upload media file",
        type=["mp3", "wav", "webm"],
        label_visibility="collapsed",
    )
    print(f"Audio uploaded: {audio_file}")
    if audio_file:
        st.session_state['result'] = None
        st.session_state['audio'] = BytesIO(audio_file.getvalue())
        st.session_state['mimetype'] = audio_file.type
    else:
        st.session_state['audio'] = None
        st.session_state['mimetype'] = None

elif audio_source == "Load media from URL":
    url = st.text_input(
        "URL",
        key="url",
        value="https://www.youtube.com/watch?v=4HGNqFdaD34",
    )

    if url != "":
        st.session_state["audio"] = None
        try:
            if "youtube.com" in url or "youtu.be" in url:
                print("Reading audio from YouTube")
                with st.spinner("Loading Youtube video..."):
                    st.session_state['result'] = None
                    st.video(url)
                    buffer, mimetype = read_from_youtube(url)
                    st.session_state["audio"] = buffer
                    st.session_state['mimetype'] = mimetype
            else:
                print("Reading audio from URL")
                with st.spinner("Loading audio URL..."):
                    st.session_state['result'] = None
                    st.session_state["audio"] = read_from_url(url)
                    st.session_state['mimetype'] = "audio/wav"
                    st.audio(st.session_state["audio"])
                print(f"Audio bytes: {st.session_state['audio'].getbuffer().nbytes} bytes")
        except Exception as e:
            raise e
            st.error(e)
            st.error("Invalid URL entered.")

else:
    audio = audiorecorder("Click to record", "Click to stop recording", show_visualizer=True, key="audio-recorder")
    if len(audio) != 0:
        print(f"Audio recorded: {audio}, length {len(audio)}")
        st.session_state["result"] = None
        with st.spinner("Processing audio..."):
            audio_bytes = BytesIO()
            audio.export(audio_bytes, format="wav")
            st.session_state["audio"] = audio_bytes
            st.audio(audio_bytes)
            st.session_state['mimetype'] = "audio/wav"
            st.session_state["audio"].seek(0)
    else:
        st.session_state['audio'] = None
        st.session_state['mimetype'] = None


options = {
    "model": ASR_MODELS[asr_model],
    list(lang_options.keys())[0]: list(lang_options.values())[0],
}


@st.experimental_fragment
def transcribe_container():
    global transcribe_button_container, transcribe_status, transcribe_button, VECTOR_INDEX
    transcribe_button_container = stylable_container(
        key="transcribe_button",
        css_styles=button_css
    )
    transcribe_status = stylable_container(key="details",css_styles=transcript_container).empty()
    user_input = ""
    # Buttons with styling
    transcribe_button = transcribe_button_container.button("Transcribe", use_container_width=True, type="primary")
    if st.session_state['audio']:
        if transcribe_button:
            try:
                with transcribe_status.status("Transcribing", expanded=True) as transcribe_status:
                    output = prerecorded({"buffer": st.session_state["audio"], "mimetype": st.session_state.get("mimetype", "audio/wav")}, options['model'], options)
                    st.session_state.result = output['text']
                    transcribe_button_container.download_button("Download Transcript", data=st.session_state.result, type="primary", file_name="transcript.txt")
                    time_taken = output['time_taken']
                    transcribe_status.update(label=f"_Completed in {round(time_taken, 2)}s_", state='complete')
                    if st.session_state.result:
                        st.write(st.session_state.result)
                    with st.spinner("Indexing documents..."):
                        print(f"Indexing transcript to vectorstore...")
                        VECTOR_INDEX = create_vectorstore(st.session_state.result)
            except Exception as e:
                raise e
                transcribe_status.update(label="Error", state='error')
                st.error("Something went wrong :/")

@st.experimental_fragment
def chat_container():
    global user_input, transcribe_status, VECTOR_INDEX
    if st.session_state.get('audio'):
        user_input = st.chat_input(placeholder="Ask a question about the transcript:")
    else:
        user_input = ""

    groq_m = GROQ_MODELS[groq_model]
    if user_input:
        if not st.session_state.get("result"):
            try:
                with transcribe_status.status("Transcribing", expanded=True) as transcribe_status:
                    output = prerecorded({"buffer": st.session_state["audio"], "mimetype": st.session_state.get("mimetype", "audio/wav")}, options['model'], options)
                    st.session_state.result = output['text']
                    #TODO: download button does not work if user chats multiple times
                    transcribe_button_container.download_button("Download Transcript", data=st.session_state.result, type="primary", file_name="transcript.txt")
                    time_taken = output['time_taken']
                    transcribe_status.update(label=f"_Completed in {round(time_taken, 2)}s_", state='complete')
                    if st.session_state.result:
                        st.write(st.session_state.result)
                    with st.spinner("Indexing documents..."):
                        VECTOR_INDEX = create_vectorstore(st.session_state.result)
            except Exception as e:
                raise e
                transcribe_status.update(label="Error", state='error')
                st.error("Something went wrong :/")
        
        # Chat
        if len(st.session_state.result) <= 2000:
            print("Stuffing whole transcript into system prompt")
            context = st.session_state.result
        else:
            # Find most similar documents
            print("Using RAG pipeline")
            retriever = VECTOR_INDEX.as_retriever(similarity_top_k=3)
            nodes = retriever.retrieve(user_input)
            context = ""
            for node in nodes:
                context += node.text + "\n"

        try:
            prompt = f"""
            {user_input}
            """
            messages=[
                {"role": "system", "content": f"""\
You are helpful assistant that answers questions based on this transcript:
```
{context}
```
Answer questions that the user asks only about the transcript and nothing else. \
Do not include the user's question in your response, only respond with your answer. \
Your responses should be in markdown. \
"""},
                {"role": "user", "content": prompt},
            ]
            model=groq_m
            gen = chat_stream(model, messages)
            if transcribe_status:
                transcribe_status.update(expanded=False)
            with st.chat_message("ai", avatar="./static/ai_avatar.png"):
                st.write_stream(gen)
        except Exception as e:
            raise e
            st.error("Something went wrong:/")
    return

transcribe_container()
chat_container()
