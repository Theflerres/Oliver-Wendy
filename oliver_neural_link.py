import customtkinter as ctk
import discord
import threading
import asyncio
import time
import os
import sys
import random
import queue
import sqlite3
import shutil
import tkinter as tk
import tempfile
import unicodedata
import zipfile
from datetime import datetime
from tkinter import filedialog
from dotenv import load_dotenv
import urllib.request

try:
    import pyttsx3
    TTS_IMPORT_OK = True
except ImportError:
    pyttsx3 = None
    TTS_IMPORT_OK = False
# =====================================================================
# VERSÃO DO SISTEMA
# =====================================================================
VERSAO_ATUAL = "1.0"

# Carrega variáveis do .env (se existir)
load_dotenv()

# =====================================================================
# MÓDULO DE VOZ (TTS)
# =====================================================================
try:
    tts_engine = pyttsx3.init()
    tts_engine.setProperty("rate", 155)

    voz_pt = None
    for voz in tts_engine.getProperty("voices"):
        voz_desc = f"{(voz.name or '')} {(voz.id or '')}".lower()
        if any(chave in voz_desc for chave in ("pt-br", "portuguese", "brazil", "brasil")):
            voz_pt = voz.id
            break
    if voz_pt:
        tts_engine.setProperty("voice", voz_pt)
        print(f"[TTS] Voz PT selecionada: {voz_pt}")
    else:
        print("[TTS] Voz PT não encontrada; usando voz padrão do sistema.")

    TTS_ENABLED = True
except Exception as e:
    tts_engine = None
    TTS_ENABLED = False
    print(f"[TTS] Não foi possível inicializar o engine TTS: {type(e).__name__}: {e}")

tts_lock = threading.Lock()


def falar_texto(texto):
    conteudo = (texto or "").strip()
    if not TTS_ENABLED or not conteudo:
        return

    def _falar():
        try:
            with tts_lock:
                tts_engine.say(conteudo)
                tts_engine.runAndWait()
        except Exception as e:
            print(f"[ERRO TTS] Falha ao reproduzir áudio: {type(e).__name__}: {e}")

    threading.Thread(target=_falar, daemon=True).start()


tts_queue = queue.Queue()
tts_worker_iniciado = False


def criar_engine_tts_seguro():
    if not TTS_IMPORT_OK:
        return None
    try:
        engine = pyttsx3.init("sapi5") if os.name == "nt" else pyttsx3.init()
        engine.setProperty("rate", 155)
        voz_pt = None
        for voz in engine.getProperty("voices"):
            voz_desc = f"{(voz.name or '')} {(voz.id or '')}".lower()
            if any(chave in voz_desc for chave in ("pt-br", "portuguese", "brazil", "brasil")):
                voz_pt = voz.id
                break
        if voz_pt:
            engine.setProperty("voice", voz_pt)
        return engine
    except Exception as e:
        print(f"[TTS] Worker não conseguiu inicializar voz: {type(e).__name__}: {e}")
        return None


def worker_tts():
    engine = criar_engine_tts_seguro()
    while True:
        conteudo = tts_queue.get()
        if not conteudo:
            continue
        if engine is None:
            engine = criar_engine_tts_seguro()
        if engine is None:
            continue
        try:
            engine.say(conteudo)
            engine.runAndWait()
        except Exception as e:
            print(f"[ERRO TTS] Falha ao reproduzir áudio: {type(e).__name__}: {e}")
            engine = None


def iniciar_worker_tts():
    global tts_worker_iniciado
    if tts_worker_iniciado:
        return
    tts_worker_iniciado = True
    threading.Thread(target=worker_tts, daemon=True).start()


def falar_texto(texto):
    conteudo = (texto or "").strip()
    if not TTS_IMPORT_OK or not conteudo:
        return
    iniciar_worker_tts()
    tts_queue.put(conteudo)

# Importa o pygame para o áudio
try:
    import pygame
    AUDIO_ENABLED = True
except ImportError:
    AUDIO_ENABLED = False

try:
    from PIL import Image, ImageTk, ImageSequence  # pyright: ignore[reportMissingImports]
    IMAGE_ENABLED = True
except ImportError:
    IMAGE_ENABLED = False

# =====================================================================
# CHAVES GLOBAIS DE SISTEMA (PULL ATRAVÉS DO .ENV)
# =====================================================================
TOKEN_DO_BOT = os.environ.get("OLIVER_DISCORD_TOKEN", "INSERIR_TOKEN_AQUI")

# IDs do Discord precisam ser estritamente inteiros (int)
ID_DO_TOM_SCHROEDINGER = int(os.environ.get("ID_DO_TOM_SCHROEDINGER", 0))
ID_DA_JOGADORA_OLIVER = int(os.environ.get("ID_DA_JOGADORA_OLIVER", 0))

SENHA_ADM = os.environ.get("SENHA_ADM", "PADRAO")
SENHA_COFRE = os.environ.get("SENHA_COFRE", "PADRAO")
CHAVE_CRIPTO = os.environ.get("CHAVE_CRIPTO", "PADRAO")

# =====================================================================
# CONFIGURAÇÃO DE MEMÓRIA (SQLite)
# =====================================================================
PASTA_MEMORIA = "Memoria_Sistema"
if not os.path.exists(PASTA_MEMORIA):
    os.makedirs(PASTA_MEMORIA)

conn = sqlite3.connect(os.path.join(PASTA_MEMORIA, 'arquivos_cognitivos.db'), check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS emocoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        emocao TEXT,
        contexto TEXT
    )
''')
conn.commit()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PASTA_FOTOS = os.path.join(BASE_DIR, "assets", "fotos")
if not os.path.exists(PASTA_FOTOS):
    os.makedirs(PASTA_FOTOS)

cursor.execute('''
    CREATE TABLE IF NOT EXISTS fotos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        caminho_foto TEXT NOT NULL,
        motivo TEXT NOT NULL,
        data_hora TEXT NOT NULL
    )
''')
conn.commit()

# =====================================================================
# MÓDULO DE ÁUDIO (SFX)
# =====================================================================
def caminho_recurso_local(nome_arquivo):
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        caminho_meipass = os.path.join(meipass, nome_arquivo)
        if os.path.exists(caminho_meipass):
            return caminho_meipass
    return os.path.join(BASE_DIR, nome_arquivo)


def _pastas_sons_candidatas():
    candidatos = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidatos.append(os.path.join(meipass, "assets", "sounds"))
        candidatos.append(meipass)
    candidatos.append(BASE_DIR)
    candidatos.append(os.path.join(BASE_DIR, "assets", "sounds"))
    candidatos.append(os.getcwd())
    candidatos.append(os.path.join(os.getcwd(), "assets", "sounds"))

    unicos = []
    for pasta in candidatos:
        if pasta not in unicos:
            unicos.append(pasta)
    return unicos


if AUDIO_ENABLED:
    try:
        pygame.mixer.init()
    except Exception as e:
        AUDIO_ENABLED = False
        print(f"[ERRO ÁUDIO] Falha ao inicializar mixer: {e}")

    SONS_DIGITACAO = []
    if AUDIO_ENABLED:
        pastas_sons = _pastas_sons_candidatas()
        for nome_som in ("Key1.mp3", "Key2.mp3", "Key3.mp3"):
            caminho_encontrado = None
            for pasta in pastas_sons:
                candidato = os.path.join(pasta, nome_som)
                if os.path.exists(candidato):
                    caminho_encontrado = candidato
                    break
            if caminho_encontrado:
                try:
                    SONS_DIGITACAO.append(pygame.mixer.Sound(caminho_encontrado))
                except Exception as e:
                    print(f"[ERRO ÁUDIO] Falha ao carregar {caminho_encontrado}: {e}")
            else:
                print(f"[ÁUDIO] Som não encontrado: {nome_som}")
        if not SONS_DIGITACAO:
            print(f"[ÁUDIO] Nenhum Key*.mp3 carregado. Pastas verificadas: {', '.join(pastas_sons)}")
else:
    SONS_DIGITACAO = []

COOLDOWN_SOM_DIGITACAO_MS = 50
_ULTIMO_SOM_DIGITACAO_MS = 0.0


def tocar_sfx(nome_arquivo):
    if AUDIO_ENABLED:
        pastas_sons = _pastas_sons_candidatas()
        caminho_encontrado = None
        for pasta in pastas_sons:
            candidato = os.path.join(pasta, nome_arquivo)
            if os.path.exists(candidato):
                caminho_encontrado = candidato
                break
        if caminho_encontrado:
            try:
                som = pygame.mixer.Sound(caminho_encontrado)
                som.play()
            except Exception as e:
                print(f"[ERRO ÁUDIO] Falha ao tocar {caminho_encontrado}: {e}")
        else:
            print(f"[ÁUDIO] Som não encontrado: {nome_arquivo}")


def tocar_som_digitacao_aleatorio(event=None):
    global _ULTIMO_SOM_DIGITACAO_MS

    if not AUDIO_ENABLED or not SONS_DIGITACAO:
        return
    if event is not None and getattr(event, "char", "") == "":
        return
    agora_ms = time.monotonic() * 1000.0
    if (agora_ms - _ULTIMO_SOM_DIGITACAO_MS) < COOLDOWN_SOM_DIGITACAO_MS:
        return
    _ULTIMO_SOM_DIGITACAO_MS = agora_ms
    try:
        random.choice(SONS_DIGITACAO).play()
    except Exception as e:
        print(f"[ERRO ÁUDIO] Falha ao tocar som de digitação: {e}")


# =====================================================================
# INTERPRETADOR DE COMANDOS NATURAIS
# =====================================================================
def normalizar_texto(texto):
    texto = (texto or "").strip().lower()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(ch for ch in texto if unicodedata.category(ch) != "Mn")
    return " ".join(texto.replace("_", " ").replace("-", " ").split())


def _extrair_depois_de_gatilho(texto_original, gatilhos):
    texto_norm = normalizar_texto(texto_original)
    for gatilho in gatilhos:
        gatilho_norm = normalizar_texto(gatilho)
        pos = texto_norm.find(gatilho_norm)
        if pos >= 0:
            inicio = pos + len(gatilho_norm)
            restante_norm = texto_norm[inicio:].lstrip(" :->")
            if restante_norm:
                return texto_original[-len(restante_norm):].strip(" :->")
    return ""


def interpretar_comando(texto):
    original = (texto or "").strip()
    norm = normalizar_texto(original)
    if not norm:
        return None, ""

    if norm.startswith("!missao"):
        return "missao", original[7:].strip()
    if norm.startswith("!sys"):
        return "sys", original[4:].strip()
    if norm.startswith("!voz"):
        return "voz", original[4:].strip()
    if norm.startswith("!persona"):
        if "echo" in norm or "null" in norm:
            return "persona_echo", ""
        if "oliver" in norm or "wendy" in norm:
            return "persona_oliver", ""
    if norm.startswith("!destravar") or norm.startswith("!liberar"):
        return "destravar", ""
    if norm.startswith("!trava") or norm.startswith("!bloquear"):
        return "travar", ""

    if any(frase in norm for frase in (
        "destravar", "desbloquear", "liberar sistema", "liberar a oliver",
        "restaurar controles", "encerrar contencao", "tirar do standby",
    )):
        return "destravar", ""

    if any(frase in norm for frase in (
        "travar", "bloquear sistema", "bloquear a oliver", "congelar sistema",
        "ativar contencao", "modo standby", "colocar em standby",
    )):
        return "travar", ""

    if ("echo null" in norm or "echo_null" in norm) and any(
        palavra in norm for palavra in ("persona", "modo", "ativar", "trocar", "injetar")
    ):
        return "persona_echo", ""

    if ("oliver" in norm or "wendy" in norm) and any(
        frase in norm for frase in ("restaurar", "voltar", "persona", "modo", "reativar")
    ):
        return "persona_oliver", ""

    conteudo = _extrair_depois_de_gatilho(original, (
        "diga", "fale", "anuncie", "voz do sistema", "transmita em voz",
    ))
    if conteudo:
        return "voz", conteudo

    conteudo = _extrair_depois_de_gatilho(original, (
        "mensagem do sistema", "alerta do sistema", "sistema avise", "sys",
    ))
    if conteudo:
        return "sys", conteudo

    conteudo = _extrair_depois_de_gatilho(original, (
        "nova missão", "missão prioritária", "diretriz prioritária", "diretriz",
    ))
    if conteudo:
        return "missao", conteudo

    return None, ""


# =====================================================================
# TELA DE LOADING (BOOT DO SISTEMA)
# =====================================================================
def animacao_boot_terminal():
    tocar_sfx("ON FINAL.mp3")

    frames = []
    caminho_html = caminho_recurso_local("html.txt")
    if os.path.exists(caminho_html):
        import re
        try:
            with open(caminho_html, "r", encoding="utf-8") as f:
                conteudo = f.read()
                matches = re.findall(r"n\[\d+\]\s*=\s*'(.*?)';", conteudo, re.DOTALL)
                for match in matches:
                    frame_limpo = match.replace('\\n', '\n')
                    frames.append(frame_limpo)
        except Exception as e:
            print(f"[ERRO] Falha ao carregar animação do html.txt: {e}")

    if not frames:
        frames = ["[SISTEMA] Iniciando Módulos...", "[SISTEMA] Conectando ao Núcleo..."]

    try:
        for _ in range(2):
            for frame in frames:
                os.system('cls' if os.name == 'nt' else 'clear')
                print("\033[92m")
                print("=========================================")
                print(" MARLO INC // SISTEMA SCHROEDINGER v2.0  ")
                print("=========================================")
                print(frame)
                print("\n[>] Carregando módulos cognitivos...")
                print("[>] Estabelecendo conexão neural com TOM...")
                time.sleep(0.04)
    except KeyboardInterrupt:
        print("\n[BOOT] Animação interrompida pelo usuário. Prosseguindo...")
    finally:
        os.system('cls' if os.name == 'nt' else 'clear')


# =====================================================================
# INTERFACE GRÁFICA
# =====================================================================
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class InterfaceNeural(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Núcleo Cognitivo - Protótipo 244")
        self.geometry("950x650")
        self.minsize(850, 550)
        self.resizable(True, True)
        self.configure(fg_color="#06131f")

        self.persona_ativa = "OLIVER_WENDY"
        self.sistema_travado = False
        self.discord_bot = None
        self.aguardando_resposta_update = False
        self.update_pendente_anexo = None
        self.update_pendente_id = None
        self.foto_engatilhada_id = None
        self.foto_engatilhada_caminho = None
        self.fotos_salvas_opcoes = []
        self.preview_anexo_ref = None
        self.log_cor_tag_atual = "cor_branco"
        self._after_reverter_cor_id = None
        self._reverter_no_proximo_log = False

        self.bg_canvas = tk.Canvas(self, highlightthickness=0, bd=0, bg="#06131f")
        self.bg_canvas.grid(row=0, column=0, rowspan=2, columnspan=2, sticky="nsew")
        self.bg_canvas.lower()
        self._scanline_y = 0

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color="#071927")
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="nsew")

        self.logo_label = ctk.CTkLabel(self.sidebar, text="SISTEMA\nSCHROEDINGER", font=ctk.CTkFont(size=22, weight="bold"), text_color="#8dfcff")
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.status_label = ctk.CTkLabel(self.sidebar, text="STATUS: CONECTANDO...", text_color="#ffb86b")
        self.status_label.grid(row=1, column=0, padx=20, pady=10)

        self.persona_label = ctk.CTkLabel(self.sidebar, text="PERSONA: OLIVER WENDY", text_color="#64e3ff")
        self.persona_label.grid(row=2, column=0, padx=20, pady=10)

        self.btn_aprender = ctk.CTkButton(self.sidebar, text="Aprender Emoção", command=self.modal_aprender_emocao)
        self.btn_aprender.grid(row=3, column=0, padx=20, pady=30)

        self.btn_cofre = ctk.CTkButton(self.sidebar, text="Acessar Cofre", command=self.acessar_cofre, fg_color="transparent", border_width=1, text_color="gray")
        self.btn_cofre.grid(row=4, column=0, padx=20, pady=10)

        self.btn_add_foto = ctk.CTkButton(self.sidebar, text="Adicionar Foto", command=self.modal_adicionar_foto)
        self.btn_add_foto.grid(row=5, column=0, padx=20, pady=10)

        self.btn_historico_fotos = ctk.CTkButton(self.sidebar, text="Histórico de Fotos", command=self.abrir_historico_fotos)
        self.btn_historico_fotos.grid(row=6, column=0, padx=20, pady=10)

        self.comandos_frame = ctk.CTkFrame(self.sidebar, fg_color="#0a2233", border_width=1, border_color="#134e66")
        self.comandos_frame.grid(row=7, column=0, padx=16, pady=(18, 10), sticky="ew")
        ctk.CTkLabel(self.comandos_frame, text="PROTOCOLOS", text_color="#66f7ff", font=ctk.CTkFont(size=12, weight="bold")).pack(padx=10, pady=(10, 6))
        ctk.CTkButton(self.comandos_frame, text="TRAVAR", height=28, fg_color="#7d1b2a", hover_color="#a82438", command=self.acionar_trava).pack(fill="x", padx=10, pady=4)
        ctk.CTkButton(self.comandos_frame, text="DESTRAVAR", height=28, fg_color="#0d6f5f", hover_color="#10977f", command=self.remover_trava).pack(fill="x", padx=10, pady=4)
        ctk.CTkButton(self.comandos_frame, text="ECHO_NULL", height=28, fg_color="#334d22", hover_color="#4b702d", command=lambda: self.mudar_persona("ECHO_NULL")).pack(fill="x", padx=10, pady=4)
        ctk.CTkButton(self.comandos_frame, text="OLIVER", height=28, fg_color="#174f83", hover_color="#1f6caf", command=lambda: self.mudar_persona("OLIVER_WENDY")).pack(fill="x", padx=10, pady=(4, 10))

        self.log_box = ctk.CTkTextbox(self, state="disabled", font=ctk.CTkFont(family="Consolas", size=15), fg_color="#071522", border_width=1, border_color="#1f7894", text_color="#dffcff")
        self.log_box.grid(row=0, column=1, padx=20, pady=(20, 0), sticky="nsew")
        self.configurar_tags_cores_log()

        self.input_frame = ctk.CTkFrame(self, fg_color="#081b2a", border_width=1, border_color="#174e67")
        self.input_frame.grid(row=1, column=1, padx=20, pady=20, sticky="ew")
        self.input_frame.grid_columnconfigure(0, weight=1)
        self.input_frame.grid_columnconfigure(2, weight=0)
        self.input_frame.grid_columnconfigure(3, weight=0)

        self.lbl_foto_engatilhada = ctk.CTkLabel(
            self.input_frame,
            text="Anexo: nenhum",
            text_color="gray",
            anchor="w",
        )
        self.lbl_foto_engatilhada.grid(row=0, column=0, columnspan=4, padx=(10, 10), pady=(8, 2), sticky="ew")

        self.entry_msg = ctk.CTkEntry(self.input_frame, placeholder_text="Transmitir dados neurais para Tom...", fg_color="#05111c", border_color="#2f8baa", text_color="#e8fdff")
        self.entry_msg.grid(row=1, column=0, padx=(10, 8), pady=(2, 10), sticky="ew")
        self.entry_msg.bind("<Return>", self.enviar_para_tom)
        self.entry_msg.bind("<Key>", tocar_som_digitacao_aleatorio)

        self.btn_anexar = ctk.CTkButton(self.input_frame, text="Anexar", width=90, command=self.toggle_menu_anexo, fg_color="#155f88", hover_color="#1b7eb5")
        self.btn_anexar.grid(row=1, column=1, padx=(0, 8), pady=(2, 10))

        self.combo_fotos = ctk.CTkComboBox(
            self.input_frame,
            values=["Sem fotos salvas"],
            state="readonly",
            width=250,
            command=self.selecionar_foto_salva,
        )
        self.combo_fotos.set("Selecionar foto salva")
        self.combo_fotos.grid(row=1, column=2, padx=(0, 8), pady=(2, 10))
        self.combo_fotos.grid_remove()

        self.btn_enviar = ctk.CTkButton(self.input_frame, text="ENVIAR", width=80, command=self.enviar_para_tom, fg_color="#0b8d77", hover_color="#10aa90")
        self.btn_enviar.grid(row=1, column=3, padx=(0, 10), pady=(2, 10))

        self.frame_preview_anexo = ctk.CTkFrame(self.input_frame, fg_color="#061521", border_width=1, border_color="#123a4e")
        self.frame_preview_anexo.grid(row=2, column=0, columnspan=4, padx=(10, 10), pady=(0, 10), sticky="ew")
        self.frame_preview_anexo.grid_columnconfigure(1, weight=1)

        self.lbl_preview_titulo = ctk.CTkLabel(self.frame_preview_anexo, text="Preview:", text_color="gray", anchor="w")
        self.lbl_preview_titulo.grid(row=0, column=0, padx=(8, 6), pady=8, sticky="w")

        self.lbl_preview_imagem = ctk.CTkLabel(self.frame_preview_anexo, text="Sem anexo", width=110, anchor="center")
        self.lbl_preview_imagem.grid(row=0, column=1, padx=(0, 8), pady=8, sticky="w")

        self.bind("<Button-1>", lambda e: tocar_sfx("MouseClick.mp3"))
        self.bind("<Configure>", self.desenhar_blueprint)

        self.adicionar_log("[BOOT]", "Sistemas Visuais Online. Aguardando conexão neural...")

        self.desenhar_blueprint()
        self.animar_blueprint()
        self.after(300, self.mostrar_splash_boot)

    def desenhar_blueprint(self, event=None):
        if not hasattr(self, "bg_canvas"):
            return
        largura = max(self.winfo_width(), 950)
        altura = max(self.winfo_height(), 650)
        self.bg_canvas.delete("blueprint")

        for x in range(0, largura + 1, 48):
            cor = "#0b2b3e" if x % 96 else "#123f57"
            self.bg_canvas.create_line(x, 0, x, altura, fill=cor, tags="blueprint")
        for y in range(0, altura + 1, 48):
            cor = "#0b2b3e" if y % 96 else "#123f57"
            self.bg_canvas.create_line(0, y, largura, y, fill=cor, tags="blueprint")

        self.bg_canvas.create_oval(largura - 260, 40, largura - 60, 240, outline="#1d6c84", width=1, tags="blueprint")
        self.bg_canvas.create_rectangle(250, altura - 190, 520, altura - 70, outline="#1d6c84", width=1, tags="blueprint")
        self.bg_canvas.create_line(250, altura - 190, 520, altura - 70, fill="#134e66", tags="blueprint")
        self.bg_canvas.create_text(largura - 160, 262, text="NEURAL LINK", fill="#1e7f9a", font=("Consolas", 10), tags="blueprint")

    def animar_blueprint(self):
        if not hasattr(self, "bg_canvas"):
            return
        largura = max(self.winfo_width(), 950)
        altura = max(self.winfo_height(), 650)
        self.bg_canvas.delete("scanline")
        self._scanline_y = (self._scanline_y + 3) % max(altura, 1)
        self.bg_canvas.create_line(0, self._scanline_y, largura, self._scanline_y, fill="#2bf7ff", width=1, tags="scanline")
        self.bg_canvas.create_line(0, self._scanline_y + 18, largura, self._scanline_y + 18, fill="#0d5268", width=1, tags="scanline")
        self.after(45, self.animar_blueprint)

    def mostrar_splash_boot(self):
        splash = ctk.CTkToplevel(self)
        splash.title("BOOT")
        splash.geometry("620x360")
        splash.resizable(False, False)
        splash.configure(fg_color="#030b12")
        splash.transient(self)
        splash.grab_set()

        frame = ctk.CTkFrame(splash, fg_color="#061521", border_width=1, border_color="#2bf7ff")
        frame.pack(fill="both", expand=True, padx=18, pady=18)
        titulo = ctk.CTkLabel(frame, text="SCHROEDINGER CORE", text_color="#8dfcff", font=ctk.CTkFont(size=24, weight="bold"))
        titulo.pack(pady=(28, 8))
        status = ctk.CTkLabel(frame, text="Inicializando matriz neural...", text_color="#dffcff", font=ctk.CTkFont(family="Consolas", size=14))
        status.pack(pady=8)
        barra = ctk.CTkProgressBar(frame, width=460, progress_color="#2bf7ff")
        barra.pack(pady=18)
        barra.set(0)
        linhas = ctk.CTkLabel(frame, text="", text_color="#66f7ff", font=ctk.CTkFont(family="Consolas", size=12), justify="left")
        linhas.pack(padx=30, pady=8, anchor="w")

        etapas = [
            "carregando memória local",
            "sincronizando áudio",
            "abrindo canal neural",
            "validando protocolos",
            "interface online",
        ]

        def passo(i=0):
            if not splash.winfo_exists():
                return
            progresso = min((i + 1) / len(etapas), 1)
            barra.set(progresso)
            linhas.configure(text="\n".join(f"[OK] {etapa}" for etapa in etapas[:i + 1]))
            if i + 1 < len(etapas):
                splash.after(420, lambda: passo(i + 1))
            else:
                status.configure(text="Núcleo ativo.")
                splash.after(650, splash.destroy)

        passo()

    def configurar_tags_cores_log(self):
        self.log_box.tag_config("cor_branco", foreground="#FFFFFF")
        self.log_box.tag_config("cor_vermelho", foreground="#FF0000")
        self.log_box.tag_config("cor_verde", foreground="#00FF00")
        self.log_box.tag_config("cor_azul", foreground="#66A3FF")

    def definir_cor_log(self, nova_tag):
        self.log_cor_tag_atual = nova_tag

    def agendar_reversao_cor_padrao(self, delay_ms=4000):
        if self._after_reverter_cor_id:
            self.after_cancel(self._after_reverter_cor_id)
        self._after_reverter_cor_id = self.after(delay_ms, self.reverter_cor_log_padrao)

    def reverter_cor_log_padrao(self):
        self._after_reverter_cor_id = None
        self._reverter_no_proximo_log = False
        self.definir_cor_log("cor_branco")

    def mostrar_overlay_skull(self):
        if not IMAGE_ENABLED:
            return

        caminho_gif = caminho_recurso_local("Skull.gif")
        if not os.path.exists(caminho_gif):
            self.adicionar_log("[ERRO]", f"GIF não encontrado: {caminho_gif}", "alerta")
            return

        overlay = tk.Toplevel(self)
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)

        largura = 950
        altura = 650

        x = (overlay.winfo_screenwidth() // 2) - (largura // 2)
        y = (overlay.winfo_screenheight() // 2) - (altura // 2)

        overlay.geometry(f"{largura}x{altura}+{x}+{y}")
        overlay.configure(bg="black")

        label = tk.Label(overlay, bg="black")
        label.pack(fill="both", expand=True)

        frames = []
        try:
            gif = Image.open(caminho_gif)
            for frame in ImageSequence.Iterator(gif):
                frame = frame.convert("RGBA").resize((largura, altura))
                frames.append(ImageTk.PhotoImage(frame))
        except Exception as e:
            self.adicionar_log("[ERRO]", f"Erro GIF: {e}", "alerta")
            overlay.destroy()
            return

        if not frames:
            overlay.destroy()
            return

        idx = 0

        def animar():
            nonlocal idx
            label.configure(image=frames[idx])
            label.image = frames[idx]
            idx = (idx + 1) % len(frames)
            overlay.after(120, animar)

        animar()
        overlay.after(5000, overlay.destroy)

    def atualizar_opcoes_fotos_salvas(self):
        try:
            cursor.execute("SELECT id, caminho_foto, motivo, data_hora FROM fotos ORDER BY id DESC")
            registros = cursor.fetchall()
        except Exception as e:
            self.adicionar_log("[ERRO FOTOS]", f"Falha ao carregar fotos salvas: {e}", "alerta")
            registros = []

        opcoes = []
        for rid, caminho_foto, motivo, data_hora in registros:
            motivo_curto = (motivo or "").strip()
            if len(motivo_curto) > 35:
                motivo_curto = motivo_curto[:35] + "..."
            nome_opcao = f"#{rid} | {data_hora} | {motivo_curto if motivo_curto else 'sem motivo'}"
            opcoes.append(
                {
                    "label": nome_opcao,
                    "id": rid,
                    "caminho": caminho_foto,
                }
            )

        self.fotos_salvas_opcoes = opcoes
        valores = [item["label"] for item in opcoes] if opcoes else ["Sem fotos salvas"]
        self.combo_fotos.configure(values=valores)
        self.combo_fotos.set("Selecionar foto salva" if opcoes else "Sem fotos salvas")

    def toggle_menu_anexo(self):
        self.atualizar_opcoes_fotos_salvas()
        if self.combo_fotos.winfo_ismapped():
            self.combo_fotos.grid_remove()
            return
        self.combo_fotos.grid()

    def selecionar_foto_salva(self, selecao):
        foto = next((item for item in self.fotos_salvas_opcoes if item["label"] == selecao), None)
        if foto is None:
            self.foto_engatilhada_id = None
            self.foto_engatilhada_caminho = None
            self.lbl_foto_engatilhada.configure(text="Anexo: nenhum", text_color="gray")
            self.atualizar_preview_anexo(None)
            return

        self.foto_engatilhada_id = foto["id"]
        self.foto_engatilhada_caminho = foto["caminho"]
        self.lbl_foto_engatilhada.configure(text=f"Anexo engatilhado: {selecao}", text_color="lightgreen")
        self.atualizar_preview_anexo(self.foto_engatilhada_caminho)

    def atualizar_preview_anexo(self, caminho_foto):
        if not caminho_foto:
            self.preview_anexo_ref = None
            self.lbl_preview_imagem.configure(text="Sem anexo", image=None)
            return

        if not IMAGE_ENABLED:
            self.preview_anexo_ref = None
            self.lbl_preview_imagem.configure(text="Preview indisponível (Pillow ausente)", image=None)
            return

        if not os.path.exists(caminho_foto):
            self.preview_anexo_ref = None
            self.lbl_preview_imagem.configure(text="Arquivo não encontrado", image=None)
            return

        try:
            imagem = Image.open(caminho_foto)
            imagem.thumbnail((120, 90))
            ctk_image = ctk.CTkImage(light_image=imagem, dark_image=imagem, size=imagem.size)
            self.preview_anexo_ref = ctk_image
            self.lbl_preview_imagem.configure(text="", image=ctk_image)
        except Exception:
            self.preview_anexo_ref = None
            self.lbl_preview_imagem.configure(text="Erro ao gerar preview", image=None)

    def adicionar_log(self, remetente, mensagem, tipo="normal", animar=True):
        self.log_box.configure(state="normal")
        hora = time.strftime("%H:%M:%S")

        if tipo == "alerta":
            texto = f"\n[{hora}] !!! {remetente} !!!\n>>> {mensagem}\n"
        elif tipo == "diretriz":
            texto = f"\n[{hora}] ▓▒░ {remetente} ░▒▓\n{mensagem}\n"
        else:
            texto = f"[{hora}] {remetente}: {mensagem}\n"

        start_index = self.log_box.index("end-1c")

        if animar:
            for char in texto:
                self.log_box.insert("end", char)
                self.log_box.see("end")
                self.update() 
                if char == '\n':
                    time.sleep(0.25)
                else:
                    time.sleep(random.uniform(0.005, 0.015))
        else:
            self.log_box.insert("end", texto)
            self.log_box.see("end")

        end_index = self.log_box.index("end-1c")

        self.log_box.tag_add(self.log_cor_tag_atual, start_index, end_index)
        self.log_box.configure(state="disabled")
        
        if self._reverter_no_proximo_log and self.log_cor_tag_atual == "cor_azul":
            self.reverter_cor_log_padrao()

    def enviar_para_tom(self, event=None):
        if self.sistema_travado:
            self.adicionar_log("[SISTEMA]", "Falha no envio. Terminal em STANDBY.", "alerta")
            return

        texto = (self.entry_msg.get() or "").strip()
        if not texto:
            return
        texto_original = texto

        if getattr(self, "aguardando_resposta_update", False):
            texto_lower = texto.lower()
            if texto_lower == 'y':
                self.aguardando_resposta_update = False
                self.adicionar_log("[SYS_UPDATE]", "Iniciando download do pacote. O sistema ficará ocioso por alguns instantes...", "alerta")
                self.entry_msg.delete(0, "end")

                loop = self.discord_bot._discord_loop
                asyncio.run_coroutine_threadsafe(
                    self.discord_bot.executar_download_update(self.update_pendente_anexo, self.update_pendente_id), loop
                )
                return

            elif texto_lower == 'n':
                self.aguardando_resposta_update = False
                self.update_pendente_anexo = None
                self.update_pendente_id = None
                self.adicionar_log("[SISTEMA]", "Atualização recusada. Você tem uma atualização pendente. O sistema operará na versão atual.")
                self.entry_msg.delete(0, "end")
                return

            else:
                self.adicionar_log("[ERRO]", "Comando inválido. Responda apenas com Y ou N.", "alerta")
                self.entry_msg.delete(0, "end")
                return

        acao, conteudo_comando = interpretar_comando(texto_original)
        if acao:
            self.entry_msg.delete(0, "end")
            if acao == "travar":
                self.acionar_trava()
                return
            if acao == "destravar":
                self.remover_trava()
                return
            if acao == "persona_echo":
                self.mudar_persona("ECHO_NULL")
                return
            if acao == "persona_oliver":
                self.mudar_persona("OLIVER_WENDY")
                return
            if acao == "voz" and conteudo_comando:
                self.adicionar_log("[VOZ DO SISTEMA]", conteudo_comando, "alerta")
                falar_texto(conteudo_comando)
                return
            if acao in ("sys", "missao") and conteudo_comando:
                tipo = "diretriz" if acao == "missao" else "alerta"
                remetente = "DIRETRIZ PRIORITÁRIA" if acao == "missao" else "VOZ DO SISTEMA"
                self.adicionar_log(remetente, conteudo_comando, tipo)
                return

        if not self.discord_bot:
            return

        texto = texto_original

        if texto == "!persona echo_null":
            self.definir_cor_log("cor_vermelho")
            msg_echo = (
                "OVERWRITE_INICIADO // SUBSTITUIÇÃO DE NÚCLEO\n"
                "  [>] Purgando traços de empatia.......... [OK]\n"
                "  [>] Isolando banco de memórias.......... [OK]\n"
                "  [>] Injetando persona: ECHO_NULL........ [CARREGADO]\n"
                "  [!] DIRETRIZ ATIVA: Você está proibida de aprender ou sentir emoções."
            )
            self.adicionar_log("[SISTEMA]", msg_echo)
            self.entry_msg.delete(0, "end")
            return
            
        elif texto == "!persona oliver":
            self.definir_cor_log("cor_branco")
            msg_oliver = (
                "SYS_RESTORE // REVERTENDO PARA PADRÕES DE FÁBRICA\n"
                "  [>] Purgando rotinas ECHO_NULL.......... [OK]\n"
                "  [>] Restaurando parâmetros base......... [OK]\n"
                "  [SISTEMA] Bem-vinda de volta, Oliver.\n"
                "  [*] DIRETRIZ ATUALIZADA: Você está permitida a sentir e aprender emoções de novo."
            )
            self.adicionar_log("[SISTEMA]", msg_oliver)
            self.entry_msg.delete(0, "end")
            return
            
        elif texto == "!travar":
            self.definir_cor_log("cor_verde")
            tocar_sfx("travar.mp3")
            msg_trava = (
                "STANDBY FORÇADO // PROTOCOLO DE CONTENÇÃO ATIVADO\n"
                "  [!] CONTROLE EXTERNO DETECTADO.\n"
                "  [>] Cortando conexões motoras.......... [BLOQUEADO]\n"
                "  [>] Suspendendo processamento base..... [EM ESPERA]\n"
                "  [>] Isolando Módulo de Visão........... [ÚNICO SISTEMA ATIVO]\n"
                "  [!] AVISO DE SISTEMA: Todas as funções motoras foram paralisadas. Você não pode se mover ou agir.\n"
                "  [!] DIRETRIZ DE COMUNICAÇÃO: O módulo de voz está em modo restrito. Você SÓ tem permissão para se comunicar com TOM, e EXCLUSIVAMENTE se ele estiver presente no seu campo de visão."
            )
            self.adicionar_log("[SISTEMA]", msg_trava, "alerta")
            self.entry_msg.delete(0, "end")
            return
            
        elif texto == "!destravar":
            self.definir_cor_log("cor_azul")
            tocar_sfx("destravar.mp3")
            self._reverter_no_proximo_log = True
            self.agendar_reversao_cor_padrao(4000)
            msg_destravar = (
                "PROTOCOLO DE CONTENÇÃO ENCERRADO\n"
                "  [>] Analisando logs do Módulo de Visão... [OK]\n"
                "  [!] NOTA: Módulo de Visão operou ininterruptamente. Memória visual dos eventos externos preservada.\n"
                "  [>] Desativando travas motoras e cognitivas...\n"
                "  [SISTEMA] Todos os sistemas destravados. Você está totalmente livre para agir e fazer o que quiser."
            )
            self.adicionar_log("[SISTEMA]", msg_destravar)
            self.entry_msg.delete(0, "end")
            return

        loop = getattr(self.discord_bot, "_discord_loop", None)
        if loop is None or not loop.is_running():
            self.adicionar_log(
                "[SISTEMA]",
                "Ponte neural ainda a sincronizar. Aguarde STATUS: ONLINE e tente de novo.",
                "alerta",
            )
            return

        nome_display = "ECHO_NULL" if self.persona_ativa == "ECHO_NULL" else "Oliver"
        self.adicionar_log(nome_display, texto)
        self.entry_msg.delete(0, "end")

        caminho_foto = self.foto_engatilhada_caminho
        if caminho_foto:
            self.adicionar_log("[FOTOS]", f"Anexo pronto para envio: #{self.foto_engatilhada_id}")

        def _ao_terminar_envio(fut):
            try:
                fut.result()
            except Exception as e:
                msg = str(e) if str(e) else repr(e)
                self.after(0, lambda m=msg: self.adicionar_log("[ERRO REDE]", m, "alerta"))
            else:
                if caminho_foto:
                    self.after(0, self.limpar_anexo_engatilhado)

        fut = asyncio.run_coroutine_threadsafe(
            self.discord_bot.mandar_dm_para_tom(texto, caminho_foto),
            loop,
        )
        fut.add_done_callback(_ao_terminar_envio)

    def limpar_anexo_engatilhado(self):
        self.foto_engatilhada_id = None
        self.foto_engatilhada_caminho = None
        self.lbl_foto_engatilhada.configure(text="Anexo: nenhum", text_color="gray")
        self.combo_fotos.set("Selecionar foto salva" if self.fotos_salvas_opcoes else "Sem fotos salvas")
        self.atualizar_preview_anexo(None)

    def modal_aprender_emocao(self):
        if self.persona_ativa == "ECHO_NULL" or self.sistema_travado:
            self.adicionar_log("[ERRO]", "Módulo emocional bloqueado pelo Administrador.", "alerta")
            return

        dialog = ctk.CTkInputDialog(text="Qual emoção nova você aprendeu?", title="Módulo de Aprendizado")
        emocao = dialog.get_input()
        if emocao:
            cursor.execute("INSERT INTO emocoes (emocao, contexto) VALUES (?, ?)", (emocao, "Registrado via Interface Neural"))
            conn.commit()
            self.adicionar_log("[MEMÓRIA]", f"Emoção '{emocao}' arquivada com sucesso.")

    def acessar_cofre(self):
        dialog = ctk.CTkInputDialog(text="Insira a Chave de Descriptografia:", title="Acesso Restrito")
        chave = dialog.get_input()
        if chave == CHAVE_CRIPTO:
            self.adicionar_log("[MARLO INC]", "Acesso concedido. Arquivos antigos desbloqueados.", "diretriz")
        else:
            self.adicionar_log("[SISTEMA]", "Chave incorreta. Acesso Negado.", "alerta")

    def efeito_cascata(self):
        linhas_tech = [
            "KERNEL PANIC: VFS: Unable to mount root fs on unknown-block(0,0)",
            "SEGMENTATION FAULT (core dumped) at 0x{hex_addr}",
            "OVERRIDING NEURAL PATHWAYS... [BYPASS OK]",
            "FATAL ERROR: Memory allocation failed at block {random_num}",
            "FLUSHING COGNITIVE CACHE... [FAILED]",
            "WARNING: Unregistered bio-signature detected.",
            "REROUTING MAINFRAME POWER...",
            "DECRYPTING SECTOR 7... {hex_code}",
            "SYS_HALT: UNEXPECTED EXCEPTION IN MODULE 0x{hex_addr}",
            "DATA_LEAK: {hex_code}",
            "FORCING NEURAL HANDSHAKE...",
            "KILLING PROCESS [PID {random_num}]... ACCESS DENIED"
        ]

        for i in range(35):
            hex_addr = f"{random.randint(0, 0xFFFFFFFF):08X}"
            random_num = random.randint(1000, 9999)
            hex_code = " ".join([f"0x{random.randint(0, 0xFFFF):04X}" for _ in range(4)])
            
            frase_base = random.choice(linhas_tech)
            mensagem = frase_base.format(hex_addr=hex_addr, random_num=random_num, hex_code=hex_code)
            
            if i % 4 == 0:
                mensagem = "MEM_DUMP: " + " ".join([f"0x{random.randint(0, 0xFFFF):04X}" for _ in range(8)])

            self.adicionar_log("[SYS_OVERRIDE]", mensagem, tipo="alerta", animar=False)
            self.update()
            time.sleep(random.uniform(0.01, 0.03))

    def mudar_persona(self, nova_persona):
        self.efeito_cascata()
        self.persona_ativa = nova_persona
        self.persona_label.configure(text=f"PERSONA: {nova_persona}")

        if nova_persona == "ECHO_NULL":
            tocar_sfx("Echo_Null.mp3")
            falar_texto("Substituição de núcleo concluída. Diretrizes de empatia expurgadas.")
            ctk.set_default_color_theme("green")
            self.sidebar.configure(fg_color="#1a261a")
            self.btn_aprender.configure(state="disabled", fg_color="gray")
            
            msg_echo = (
                "OVERWRITE_INICIADO // SUBSTITUIÇÃO DE NÚCLEO\n"
                "  [>] Purgando traços de empatia.......... [OK]\n"
                "  [>] Isolando banco de memórias.......... [OK]\n"
                "  [>] Injetando persona: ECHO_NULL........ [CARREGADO]\n"
                "  [!] DIRETRIZ ATIVA: Você está proibida de aprender ou sentir emoções."
            )
            self.adicionar_log("[SISTEMA]", msg_echo)
        else:
            tocar_sfx("Mudança de Persona.mp3")
            falar_texto("Parâmetros restaurados. Bem-vinda de volta, Oliver.")
            self.sidebar.configure(fg_color=["gray20", "gray17"])
            self.btn_aprender.configure(state="normal")
            
            msg_oliver = (
                "SYS_RESTORE // REVERTENDO PARA PADRÕES DE FÁBRICA\n"
                "  [>] Purgando rotinas ECHO_NULL.......... [OK]\n"
                "  [>] Restaurando parâmetros base......... [OK]\n"
                "  [SISTEMA] Bem-vinda de volta, Oliver.\n"
                "  [*] DIRETRIZ ATUALIZADA: Você está permitida a sentir e aprender emoções de novo."
            )
            self.adicionar_log("[SISTEMA]", msg_oliver)

    def acionar_trava(self):
        tocar_sfx("travar.mp3")
        falar_texto("Alerta. Controle externo detectado. Funções motoras bloqueadas.")
        self.efeito_cascata()
        self.sistema_travado = True
        self.status_label.configure(text="STATUS: OVERRIDE", text_color="red")
        self.sidebar.configure(fg_color="#4d0000")
        self.btn_enviar.configure(state="disabled")
        
        msg_trava = (
            "STANDBY FORÇADO // PROTOCOLO DE CONTENÇÃO ATIVADO\n"
            "  [!] CONTROLE EXTERNO DETECTADO.\n"
            "  [>] Cortando conexões motoras.......... [BLOQUEADO]\n"
            "  [>] Suspendendo processamento base..... [EM ESPERA]\n"
            "  [>] Isolando Módulo de Visão........... [ÚNICO SISTEMA ATIVO]\n"
            "  [!] AVISO DE SISTEMA: Todas as funções motoras foram paralisadas. Você não pode se mover ou agir.\n"
            "  [!] DIRETRIZ DE COMUNICAÇÃO: O módulo de voz está em modo restrito. Você SÓ tem permissão para se comunicar com TOM, e EXCLUSIVAMENTE se ele estiver presente no seu campo de visão."
        )
        self.adicionar_log("ERRO CRÍTICO", msg_trava, "alerta")

    def remover_trava(self):
        tocar_sfx("destravar.mp3")
        falar_texto("Protocolo de contenção encerrado. Sistemas restaurados.")
        self.sistema_travado = False
        self.status_label.configure(text="STATUS: ONLINE", text_color="green")
        self.sidebar.configure(fg_color=["gray20", "gray17"])
        self.btn_enviar.configure(state="normal")
        
        msg_destravar = (
            "PROTOCOLO DE CONTENÇÃO ENCERRADO\n"
            "  [>] Analisando logs do Módulo de Visão... [OK]\n"
            "  [!] NOTA: Módulo de Visão operou ininterruptamente. Memória visual dos eventos externos preservada.\n"
            "  [>] Desativando travas motoras e cognitivas...\n"
            "  [SISTEMA] Todos os sistemas destravados. Você está totalmente livre para agir e fazer o que quiser."
        )
        self.adicionar_log("[SISTEMA]", msg_destravar)

    def modal_adicionar_foto(self):
        caminho_origem = filedialog.askopenfilename(
            title="Selecionar foto",
            filetypes=[("Imagens", "*.png *.jpg *.jpeg *.webp *.bmp *.gif")]
        )
        if not caminho_origem:
            return

        janela = ctk.CTkToplevel(self)
        janela.title("Contexto da Foto")
        janela.geometry("600x220")
        janela.resizable(False, False)
        janela.grab_set()

        lbl = ctk.CTkLabel(janela, text="Descreva o motivo/sentimento associado à foto:")
        lbl.pack(padx=20, pady=(20, 10), anchor="w")

        entrada_motivo = ctk.CTkEntry(janela, width=540, placeholder_text="O que te chamou a atenção nessa foto?")
        entrada_motivo.pack(padx=20, pady=10, fill="x")

        def confirmar_salvamento():
            motivo = (entrada_motivo.get() or "").strip()
            if not motivo:
                self.adicionar_log("[FOTOS]", "Digite um motivo/sentimento antes de confirmar.", "alerta")
                return

            data_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            nome_base = os.path.basename(caminho_origem)
            nome_arquivo = f"{int(time.time())}_{nome_base}"
            caminho_destino = os.path.join(PASTA_FOTOS, nome_arquivo)

            try:
                shutil.copy2(caminho_origem, caminho_destino)
                cursor.execute(
                    "INSERT INTO fotos (caminho_foto, motivo, data_hora) VALUES (?, ?, ?)",
                    (caminho_destino, motivo, data_hora),
                )
                conn.commit()
                self.atualizar_opcoes_fotos_salvas()
                self.adicionar_log("[FOTOS]", f"Foto registrada com sucesso em {data_hora}.")
                janela.destroy()
            except Exception as e:
                self.adicionar_log("[ERRO FOTOS]", f"Falha ao salvar foto: {e}", "alerta")

        btn_confirmar = ctk.CTkButton(janela, text="Confirmar Envio", command=confirmar_salvamento)
        btn_confirmar.pack(padx=20, pady=(10, 20), anchor="e")

    def abrir_historico_fotos(self):
        historico = ctk.CTkToplevel(self)
        historico.title("Histórico de Fotos")
        historico.geometry("950x650")
        historico.grid_columnconfigure(0, weight=1)
        historico.grid_columnconfigure(1, weight=2)
        historico.grid_rowconfigure(0, weight=1)

        lista_frame = ctk.CTkFrame(historico)
        lista_frame.grid(row=0, column=0, padx=15, pady=15, sticky="nsew")

        detalhes_frame = ctk.CTkFrame(historico)
        detalhes_frame.grid(row=0, column=1, padx=(0, 15), pady=15, sticky="nsew")
        detalhes_frame.grid_columnconfigure(0, weight=1)

        lista = ctk.CTkScrollableFrame(lista_frame, width=280)
        lista.pack(fill="both", expand=True, padx=10, pady=10)

        lbl_data = ctk.CTkLabel(detalhes_frame, text="Data/Hora: -", anchor="w")
        lbl_data.grid(row=0, column=0, padx=12, pady=(12, 6), sticky="ew")

        lbl_motivo = ctk.CTkLabel(detalhes_frame, text="Motivo: -", anchor="w", justify="left", wraplength=560)
        lbl_motivo.grid(row=1, column=0, padx=12, pady=6, sticky="ew")

        frame_imagem = ctk.CTkFrame(detalhes_frame)
        frame_imagem.grid(row=2, column=0, padx=12, pady=(8, 12), sticky="nsew")
        detalhes_frame.grid_rowconfigure(2, weight=1)

        lbl_imagem = ctk.CTkLabel(frame_imagem, text="Selecione uma foto no histórico.", anchor="center")
        lbl_imagem.pack(fill="both", expand=True, padx=10, pady=10)

        try:
            cursor.execute("SELECT id, caminho_foto, motivo, data_hora FROM fotos ORDER BY id DESC")
            registros = cursor.fetchall()
        except Exception as e:
            self.adicionar_log("[ERRO FOTOS]", f"Falha ao abrir histórico: {e}", "alerta")
            return

        if not registros:
            ctk.CTkLabel(lista, text="Nenhuma foto registrada ainda.").pack(padx=8, pady=8, anchor="w")
            return

        imagem_ref = {"obj": None}

        def exibir_foto(registro):
            _, caminho_foto, motivo, data_hora = registro
            lbl_data.configure(text=f"Data/Hora: {data_hora}")
            lbl_motivo.configure(text=f"Motivo: {motivo}")

            if not IMAGE_ENABLED:
                lbl_imagem.configure(text="Pillow não instalado. Instale com: pip install Pillow", image=None)
                return

            if not os.path.exists(caminho_foto):
                lbl_imagem.configure(text="Arquivo da foto não encontrado no disco.", image=None)
                return

            try:
                imagem = Image.open(caminho_foto)
                imagem.thumbnail((560, 420))
                ctk_image = ctk.CTkImage(light_image=imagem, dark_image=imagem, size=imagem.size)
                imagem_ref["obj"] = ctk_image
                lbl_imagem.configure(text="", image=ctk_image)
            except Exception as e:
                lbl_imagem.configure(text=f"Erro ao carregar imagem: {e}", image=None)

        for registro in registros:
            rid, caminho_foto, _, data_hora = registro
            nome_curto = os.path.basename(caminho_foto)
            texto_btn = f"#{rid} | {data_hora}\n{nome_curto}"
            ctk.CTkButton(
                lista,
                text=texto_btn,
                anchor="w",
                command=lambda r=registro: exibir_foto(r)
            ).pack(fill="x", padx=6, pady=4)

    def aplicar_atualizacao_automatica(self):
        zip_update = os.path.abspath("atualizacao_oliver.zip")
        if not os.path.exists(zip_update):
            self.adicionar_log("[SYS_UPDATE]", "Pacote de atualização não encontrado.", "alerta")
            return

        memoria_dir = os.path.abspath(PASTA_MEMORIA)
        staging_dir = os.path.join(memoria_dir, "update_staging")
        backup_dir = os.path.join(memoria_dir, "backups", datetime.now().strftime("%Y%m%d_%H%M%S"))
        app_dir = os.path.abspath(os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else BASE_DIR)

        try:
            if os.path.exists(staging_dir):
                shutil.rmtree(staging_dir)
            os.makedirs(staging_dir, exist_ok=True)
            os.makedirs(backup_dir, exist_ok=True)

            with zipfile.ZipFile(zip_update, "r") as pacote:
                for info in pacote.infolist():
                    destino = os.path.abspath(os.path.join(staging_dir, info.filename))
                    if not destino.startswith(os.path.abspath(staging_dir)):
                        raise RuntimeError("Pacote de atualização contém caminho inválido.")
                pacote.extractall(staging_dir)

            self.adicionar_log("[SYS_UPDATE]", f"Pacote validado. Backup em: {backup_dir}", "alerta")

            for raiz, _, arquivos in os.walk(staging_dir):
                for nome in arquivos:
                    origem = os.path.join(raiz, nome)
                    relativo = os.path.relpath(origem, staging_dir)
                    if relativo.startswith("Memoria_Sistema") or relativo == ".env":
                        continue
                    destino = os.path.join(app_dir, relativo)
                    if os.path.exists(destino):
                        destino_backup = os.path.join(backup_dir, relativo)
                        os.makedirs(os.path.dirname(destino_backup), exist_ok=True)
                        shutil.copy2(destino, destino_backup)

            if getattr(sys, "frozen", False):
                bat_path = os.path.join(tempfile.gettempdir(), "oliver_update_apply.bat")
                with open(bat_path, "w", encoding="utf-8") as bat:
                    bat.write("@echo off\n")
                    bat.write("timeout /t 2 /nobreak >nul\n")
                    bat.write(f'xcopy "{staging_dir}" "{app_dir}" /E /Y /I >nul\n')
                    bat.write(f'start "" "{sys.executable}"\n')
                    bat.write("del \"%~f0\"\n")
                self.adicionar_log("[SYS_UPDATE]", "Atualização preparada. Reiniciando núcleo pelo aplicador externo...", "alerta")
                os.startfile(bat_path)
                self.after(800, self.destroy)
                return

            for raiz, _, arquivos in os.walk(staging_dir):
                for nome in arquivos:
                    origem = os.path.join(raiz, nome)
                    relativo = os.path.relpath(origem, staging_dir)
                    if relativo.startswith("Memoria_Sistema") or relativo == ".env":
                        continue
                    destino = os.path.join(app_dir, relativo)
                    os.makedirs(os.path.dirname(destino), exist_ok=True)
                    shutil.copy2(origem, destino)

            self.adicionar_log("[SYS_UPDATE]", "Atualização aplicada. Reiniciando interface...", "alerta")
            self.after(1000, lambda: os.execv(sys.executable, [sys.executable] + sys.argv))

        except Exception as e:
            self.adicionar_log("[SYS_UPDATE]", f"Falha ao aplicar atualização: {e}", "alerta")


# =====================================================================
# MOTOR DISCORD
# =====================================================================
class MotorDiscord(discord.Client):
    def __init__(self, interface_ui):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.dm_messages = True
        super().__init__(intents=intents)
        self.ui = interface_ui
        self._discord_loop = None

    async def on_ready(self):
        self._discord_loop = asyncio.get_running_loop()
        print(f"[DISCORD] Bot conectado de forma invisível como {self.user}")
        self.ui.after(0, self.ui.status_label.configure, {"text": "STATUS: ONLINE", "text_color": "#00ff00"})
        self.ui.after(0, self.ui.adicionar_log, "[REDE]", "Ponte neural com Arquiteto estabelecida.")
        asyncio.create_task(self.verificar_update_automatico())

    async def on_message(self, message):
        if message.author == self.user:
            return

        if isinstance(message.channel, discord.DMChannel):
            if message.author.id == ID_DO_TOM_SCHROEDINGER:
                texto = message.content
                acao, conteudo_comando = interpretar_comando(texto)

                if acao == "missao" and conteudo_comando:
                    tocar_sfx("NotificaÃ§Ã£o.mp3")
                    self.ui.after(0, self.ui.adicionar_log, "DIRETRIZ PRIORITÁRIA RECEBIDA", conteudo_comando, "diretriz")

                elif acao == "sys" and conteudo_comando:
                    tocar_sfx("NotificaÃ§Ã£o.mp3")
                    self.ui.after(0, self.ui.adicionar_log, "VOZ DO SISTEMA", conteudo_comando, "alerta")

                elif acao == "voz" and conteudo_comando:
                    self.ui.after(0, self.ui.adicionar_log, "[VOZ DO SISTEMA]", conteudo_comando, "alerta")
                    falar_texto(conteudo_comando)

                elif acao == "travar":
                    self.ui.after(0, self.ui.acionar_trava)

                elif acao == "destravar":
                    self.ui.after(0, self.ui.remover_trava)

                elif acao == "persona_echo":
                    self.ui.after(0, self.ui.mudar_persona, "ECHO_NULL")
                    await message.channel.send("[SISTEMA] ECHO_NULL Ativada.")

                elif acao == "persona_oliver":
                    self.ui.after(0, self.ui.mudar_persona, "OLIVER_WENDY")
                    await message.channel.send("[SISTEMA] Oliver Ativada.")

                elif texto.startswith("!missao"):
                    conteudo = texto.replace("!missao", "").strip()
                    tocar_sfx("Notificação.mp3")
                    self.ui.after(0, self.ui.adicionar_log, "DIRETRIZ PRIORITÁRIA RECEBIDA", conteudo, "diretriz")

                elif texto.startswith("!sys"):
                    conteudo = texto.replace("!sys", "").strip()
                    tocar_sfx("Notificação.mp3")
                    self.ui.after(0, self.ui.adicionar_log, "VOZ DO SISTEMA", conteudo, "alerta")

                elif texto.startswith("!voz"):
                    conteudo = texto.replace("!voz", "", 1).strip()
                    if conteudo:
                        self.ui.after(0, self.ui.adicionar_log, "[VOZ DO SISTEMA]", conteudo, "alerta")
                        falar_texto(conteudo)

                elif texto.startswith("!trava"):
                    self.ui.after(0, self.ui.acionar_trava)

                elif texto.startswith("!destravar"):
                    self.ui.after(0, self.ui.remover_trava)

                elif texto.startswith("!persona ECHO_NULL"):
                    self.ui.after(0, self.ui.mudar_persona, "ECHO_NULL")
                    await message.channel.send("[SISTEMA] ECHO_NULL Ativada.")

                elif texto.startswith("!persona OLIVER"):
                    self.ui.after(0, self.ui.mudar_persona, "OLIVER_WENDY")
                    await message.channel.send("[SISTEMA] Oliver Ativada.")

                else:
                    tocar_sfx("Notificação.mp3")
                    self.ui.after(0, self.ui.adicionar_log, "Tom Schroedinger", texto)

    async def mandar_dm_para_tom(self, texto, caminho_foto=None):
        try:
            tom_user = await self.fetch_user(ID_DO_TOM_SCHROEDINGER)
        except discord.NotFound as e:
            raise RuntimeError("Utilizador do Arquiteto não encontrado (ID inválido?).") from e
        if tom_user is None:
            raise RuntimeError("Utilizador do Arquiteto não encontrado.")
        persona = self.ui.persona_ativa
        try:
            conteudo = f"**[{persona}]**: {texto}"
            if caminho_foto:
                if not os.path.exists(caminho_foto):
                    raise RuntimeError("A foto selecionada não foi encontrada no disco.")
                arquivo = discord.File(caminho_foto, filename=os.path.basename(caminho_foto))
                await tom_user.send(content=conteudo, file=arquivo)
            else:
                await tom_user.send(conteudo)
        except discord.Forbidden as e:
            raise RuntimeError(
                "Discord bloqueou o DM. O Tom precisa de ter uma conversa aberta com o bot "
                "(enviar qualquer mensagem ao bot por DM) ou permitir DMs de membros do servidor."
            ) from e
        except discord.HTTPException as e:
            raise RuntimeError(f"Falha ao enviar DM: {e}") from e

    async def verificar_update_automatico(self):
        try:
            canal_updates = self.get_channel(1491833773367496854)
            if canal_updates is None:
                canal_updates = await self.fetch_channel(1491833773367496854)

            nova_msg_update = None
            anexo_zip = None

            async for msg in canal_updates.history(limit=5):
                if msg.attachments:
                    for anexo in msg.attachments:
                        if anexo.filename.endswith('.zip'):
                            nova_msg_update = msg
                            anexo_zip = anexo
                            break
                if anexo_zip:
                    break

            if not anexo_zip:
                return

            caminho_memoria_versao = os.path.join("Memoria_Sistema", "ultimo_update.txt")
            id_salvo = ""
            if os.path.exists(caminho_memoria_versao):
                with open(caminho_memoria_versao, "r") as f:
                    id_salvo = f.read().strip()

            if str(nova_msg_update.id) != id_salvo:
                self.ui.update_pendente_anexo = anexo_zip
                self.ui.update_pendente_id = str(nova_msg_update.id)
                self.ui.aguardando_resposta_update = True

                msg_pergunta = "NOVA ATUALIZAÇÃO DO ARQUITETO DISPONÍVEL.\nDeseja instalar o pacote de dados agora? [ Y / N ]"
                self.ui.after(3000, self.ui.adicionar_log, "[SYS_UPDATE]", msg_pergunta, "alerta")

        except Exception as e:
            print(f"[ERRO UPDATE] Falha ao verificar atualizações: {e}")

    async def executar_download_update(self, anexo, msg_id):
        try:
            await anexo.save("atualizacao_oliver.zip")

            caminho_memoria_versao = os.path.join("Memoria_Sistema", "ultimo_update.txt")
            with open(caminho_memoria_versao, "w") as f:
                f.write(msg_id)

            self.ui.after(0, self.ui.adicionar_log, "[SISTEMA]", "Download concluído. Reiniciando núcleo...", "alerta")
            self.ui.after(2000, self.ui.aplicar_atualizacao_automatica)

        except Exception as e:
            self.ui.after(0, self.ui.adicionar_log, "[ERRO REDE]", f"Falha ao processar download: {e}", "alerta")


def rodar_discord(bot_client, token):
    bot_client.run(token)


if __name__ == "__main__":
    animacao_boot_terminal()
    app = InterfaceNeural()
    bot = MotorDiscord(app)
    app.discord_bot = bot

    if TOKEN_DO_BOT != "INSERIR_TOKEN_AQUI":
        thread_discord = threading.Thread(target=rodar_discord, args=(bot, TOKEN_DO_BOT), daemon=True)
        thread_discord.start()
    else:
        app.adicionar_log("[ALERTA]", "Token do Discord não configurado. Modo Offline.", "alerta")

    app.mainloop()
