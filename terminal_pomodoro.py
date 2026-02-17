#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sistema de Pomodoro CLI com histórico persistente em JSON e janela flutuante
"""

import json
import os
import time
import sys
import threading
import tkinter as tk
from tkinter import messagebox
from datetime import datetime, timedelta
import customtkinter as ctk
import ctypes
import subprocess


# ========================================
# CONSTANTES
# ========================================
HISTORY_FILE = "pomodoro_history.json"


# ========================================
# FUNÇÕES DE ARMAZENAMENTO
# ========================================


def load_history():
    """Carrega histórico do arquivo JSON."""
    if not os.path.exists(HISTORY_FILE):
        return []

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        print("Aviso: Arquivo de histórico corrompido. Criando novo...")
        return []
    except Exception as e:
        print(f"Erro ao carregar histórico: {e}")
        return []


def save_session(objective, session_type, minutes):
    """Salva uma sessão no histórico."""
    history = load_history()

    now = datetime.now()
    session = {"date": now.strftime("%Y-%m-%d"), "datetime_start": now.strftime("%Y-%m-%d %H:%M:%S"), "objective": objective, "type": session_type, "minutes": minutes}

    history.append(session)

    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        print("\n✓ Sessão salva com sucesso!")
    except Exception as e:
        print(f"\n✗ Erro ao salvar sessão: {e}")


# ========================================
# FUNÇÕES DE INTERFACE
# ========================================


def clear_screen():
    """Limpa a tela do terminal."""
    os.system("cls" if os.name == "nt" else "clear")


def get_int_input(prompt, min_val=None, max_val=None):
    """Solicita entrada inteira com validação."""
    while True:
        try:
            value = int(input(prompt))
            if min_val is not None and value < min_val:
                print(f"Valor deve ser maior ou igual a {min_val}")
                continue
            if max_val is not None and value > max_val:
                print(f"Valor deve ser menor ou igual a {max_val}")
                continue
            return value
        except ValueError:
            print("Entrada inválida. Digite um número.")
        except KeyboardInterrupt:
            print("\n\nOperação cancelada.")
            sys.exit(0)


def format_time(seconds):
    """Formata segundos em HH:MM:SS."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


# ========================================
# JANELA FLUTUANTE
# ========================================


class FloatingTimerWindow:
    """Janela flutuante always-on-top para exibir timer/cronômetro."""

    def __init__(self, is_timer=True, total_minutes=0):
        self.root = ctk.CTk()
        self.root.title("Pomodoro")

        # Configuração da janela
        self.root.attributes("-topmost", True)  # Sempre no topo
        self.root.resizable(False, False)  # Não permite redimensionar
        self.root.overrideredirect(True)  # Remove barra de títulos

        # Posicionar no canto inferior direito
        window_width = 150
        window_height = 170
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = screen_width - window_width - 20
        y = screen_height - window_height - 100
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")

        # Variáveis
        self.is_timer = is_timer
        self.total_seconds = total_minutes * 60 if is_timer else 0
        self.elapsed_seconds = 0
        self.running = True
        self.paused = False
        self.cancelled = False
        self.saved_minutes = None
        self.after_ids = []  # Rastrear IDs de callbacks agendados

        # Variáveis para drag/redimensionamento
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.drag_start_width = 0
        self.drag_start_height = 0
        self.resizing = False
        self.dragging = False
        self.resize_border = 5  # Pixels da borda para detecção de resize

        # Interface
        self.create_widgets()

        # Iniciar thread de contagem
        self.thread = threading.Thread(target=self.count, daemon=True)
        self.thread.start()

        # Protocolo de fechamento
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_widgets(self):
        """Cria os widgets da janela."""
        # Frame de título para arrastar a janela
        title_frame = ctk.CTkFrame(self.root, fg_color="#1A252F", height=20, corner_radius=0)
        title_frame.pack(fill=tk.X)

        title_label = ctk.CTkLabel(title_frame, text="TIMER" if self.is_timer else "CRONÔMETRO", font=("Arial", 9, "bold"), text_color="#ECF0F1")
        title_label.pack(fill=tk.X, padx=5, pady=2)

        # Bind de drag para o frame de título
        title_label.bind("<Button-1>", self.on_title_press)
        title_label.bind("<B1-Motion>", self.on_title_drag)
        title_label.bind("<ButtonRelease-1>", self.on_title_release)

        # Armazenar referência para limpeza posterior
        self.title_label = title_label

        # Frame principal
        main_frame = ctk.CTkFrame(self.root, fg_color="#2C3E50", corner_radius=0)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Label de progresso (barras) - apenas para timer
        self.progress_label = ctk.CTkLabel(main_frame, text="", font=("Courier", 12, "bold"), text_color="#3498DB")
        if self.is_timer:
            self.progress_label.pack(pady=2)

        # Label de tempo
        self.time_label = ctk.CTkLabel(main_frame, text="00:00:00", font=("Arial", 16, "bold"), text_color="#4A6988" if self.is_timer else "#2ECC71")
        self.time_label.pack(pady=5)

        # Botões de controle: Pausar/Retomar | Finalizar
        btn_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        btn_frame.pack(pady=4)

        self.pause_button = ctk.CTkButton(
            btn_frame,
            text="⏸",
            command=self.toggle_pause,
            font=("Arial", 14, "bold"),
            fg_color="#3498DB",
            hover_color="#2980B9",
            text_color="white",
            cursor="hand2",
            corner_radius=8,
            width=35,
            height=28,
        )
        self.pause_button.grid(row=0, column=0, padx=4, pady=2)

        self.finish_button = ctk.CTkButton(
            btn_frame,
            text="✓",
            command=self.finalize_action,
            font=("Arial", 15, "bold"),
            fg_color="#27AE60",
            hover_color="#229954",
            text_color="white",
            cursor="hand2",
            corner_radius=8,
            width=35,
            height=28,
        )
        self.finish_button.grid(row=0, column=1, padx=4, pady=2)

    def count(self):
        """Thread de contagem."""
        while True:
            if not self.running:
                break

            if not self.paused:
                if self.is_timer:
                    # Timer regressivo
                    remaining = self.total_seconds - self.elapsed_seconds
                    if remaining <= 0:
                        self.finish_timer()
                        break

                    # Atualizar interface
                    self.update_display(remaining)

                else:
                    # Cronômetro crescente
                    self.update_display(self.elapsed_seconds)

                time.sleep(1)
                self.elapsed_seconds += 1
            else:
                # Janela em pausa: apenas atualiza display ocasionalmente
                if self.is_timer:
                    remaining = self.total_seconds - self.elapsed_seconds
                    self.update_display(remaining)
                else:
                    self.update_display(self.elapsed_seconds)
                time.sleep(0.2)

    def update_display(self, seconds):
        """Atualiza display com tempo e progresso."""
        # Verificar se a janela ainda existe
        if not self.root.winfo_exists():
            return

        time_str = format_time(abs(seconds))

        if self.is_timer:
            # Calcular progresso (0 a 10)
            progress = int((self.elapsed_seconds / self.total_seconds) * 10)
            progress = min(progress, 10)
            bars = "#" * progress + "·" * (10 - progress)
            # Atualizar labels
            if self.root.winfo_exists():
                after_id = self.root.after(0, lambda: self.progress_label.configure(text=bars) if self.root.winfo_exists() else None)
                self.after_ids.append(after_id)

        # Atualizar label de tempo
        if self.root.winfo_exists():
            after_id = self.root.after(0, lambda: self.time_label.configure(text=time_str) if self.root.winfo_exists() else None)
            self.after_ids.append(after_id)

    def finish_timer(self):
        """Finaliza o timer com notificação."""
        self.running = False
        self.cancel_all_after()  # Cancelar todos os callbacks
        time.sleep(0.1)  # Aguardar thread finalizar

        # Atualizar display final
        try:
            if self.root.winfo_exists():
                if self.is_timer:
                    self.progress_label.configure(text="##########")
                self.time_label.configure(text="00:00:00")
                self.root.bell()
        except:
            pass

        # Mostrar notificação (bloqueia até o usuário fechar)
        messagebox.showinfo("Pomodoro Finalizado!", "🎉 Seu timer terminou!\n\nHora de fazer uma pausa!")

        # Só fecha depois que o usuário clicar OK
        self.destroy_window()

    def toggle_pause(self):
        """Alterna pausa com feedback visual animado."""
        if not self.paused:
            self.paused = True
            self.pause_button.configure(text="▶")
            self.pause_button.configure(fg_color="#E74C3C")
        else:
            self.paused = False
            self.pause_button.configure(text="⏸")
            self.pause_button.configure(fg_color="#3498DB")

        # Pulso visual de confirmação
        self.pulse_button()

    def pulse_button(self):
        """Cria um efeito de pulso no botão."""
        if not self.root.winfo_exists():
            return
        try:
            self.pause_button.configure(fg_color="#F39C12")
            after_id = self.root.after(150, lambda: self.restore_button_color())
            self.after_ids.append(after_id)
        except:
            pass

    def restore_button_color(self):
        """Restaura a cor original do botão."""
        if not self.root.winfo_exists():
            return
        try:
            color = "#E74C3C" if self.paused else "#3498DB"
            self.pause_button.configure(fg_color=color)
        except:
            pass

    def cancel_all_after(self):
        """Cancela todos os callbacks agendados e remove binds."""
        # Cancelar callbacks agendados
        for after_id in self.after_ids:
            try:
                self.root.after_cancel(after_id)
            except:
                pass
        self.after_ids.clear()

        # Remover event binds
        try:
            self.title_label.unbind("<Button-1>")
            self.title_label.unbind("<B1-Motion>")
            self.title_label.unbind("<ButtonRelease-1>")
        except:
            pass

    def destroy_window(self):
        """Destrói a janela suprimindo erros de callbacks internos do customtkinter."""
        if not self.root.winfo_exists():
            return

        # Suprimir erros de Tcl redirecionar file descriptors
        try:
            # Salvar file descriptors originais
            old_stderr_fd = os.dup(2)  # stderr

            # Abrir /dev/null (ou nul no Windows)
            null_fd = os.open(os.devnull, os.O_RDWR)

            # Redirecionar stderr para null
            os.dup2(null_fd, 2)

            # Destruir a janela
            try:
                self.root.destroy()
            finally:
                # Fechar null_fd
                os.close(null_fd)
                # Restaurar stderr
                os.dup2(old_stderr_fd, 2)
                os.close(old_stderr_fd)
        except:
            # Fallback simples
            try:
                self.root.destroy()
            except:
                pass
        try:
            self.pause_button.configure(fg_color="#F39C12")
            after_id = self.root.after(150, lambda: self.restore_button_color())
            self.after_ids.append(after_id)
        except:
            pass

    def restore_button_color(self):
        """Restaura a cor original do botão."""
        if not self.root.winfo_exists():
            return
        try:
            color = "#E74C3C" if self.paused else "#3498DB"
            self.pause_button.configure(fg_color=color)
        except:
            pass

    def finalize_action(self):
        """Finaliza a sessão e marca para salvar os minutos decorrido."""
        # Calcular minutos decorridos
        minutes = self.elapsed_seconds // 60
        # Se for timer, garantir que não ultrapasse total
        if self.is_timer:
            minutes = min(minutes, self.total_seconds // 60)

        self.saved_minutes = minutes
        self.running = False
        self.cancel_all_after()  # Cancelar todos os callbacks
        # Não marcar como cancelado para indicar "finalizar"
        self.cancelled = False
        time.sleep(0.1)  # Aguardar thread finalizar
        self.destroy_window()

    def on_closing(self):
        """Fecha a janela."""
        self.running = False
        self.cancel_all_after()  # Cancelar todos os callbacks
        time.sleep(0.1)  # Aguardar thread finalizar
        self.cancelled = True
        self.destroy_window()

    def get_elapsed_minutes(self):
        """Retorna minutos decorridos."""
        return self.elapsed_seconds // 60

    def was_cancelled(self):
        """Verifica se foi cancelado."""
        return self.cancelled

    def run(self):
        """Inicia o loop da janela."""
        self.root.mainloop()

    def on_mouse_motion(self, event):
        """Detecta movimento do mouse - apenas para atualizar cursor em áreas de movimento."""
        pass

    def on_mouse_press(self, event):
        """Inicia movimento da janela."""
        pass

    def on_mouse_drag(self, event):
        """Move a janela."""
        pass

    def on_resize_press(self, event):
        """Inicia redimensionamento pelo canto inferior direito."""
        pass

    def on_resize_drag(self, event):
        """Redimensiona a janela pelo canto inferior direito."""
        pass

    def on_mouse_release(self, event):
        """Para drag ou redimensionamento."""
        pass

    def on_title_press(self, event):
        """Inicia movimento da janela via título."""
        self.dragging = True
        self.drag_start_x = event.x_root
        self.drag_start_y = event.y_root

    def on_title_drag(self, event):
        """Move a janela via título."""
        if self.dragging:
            delta_x = event.x_root - self.drag_start_x
            delta_y = event.y_root - self.drag_start_y

            x = self.root.winfo_x() + delta_x
            y = self.root.winfo_y() + delta_y

            self.root.geometry(f"+{x}+{y}")

            self.drag_start_x = event.x_root
            self.drag_start_y = event.y_root

    def on_title_release(self, event):
        """Finaliza movimento da janela."""
        self.dragging = False


# ========================================
# MENU PRINCIPAL
# ========================================


def show_main_menu():
    """Exibe menu principal e retorna escolha."""
    print("\n" + "=" * 40)
    print("        SISTEMA POMODORO")
    print("=" * 40)
    print("\nSelecione o objetivo:")
    print("1 - Estudar")
    print("2 - Trabalhar")
    print("3 - Outros")
    print("4 - Histórico")
    print("0 - Sair")

    choice = get_int_input("\nEscolha: ", 0, 4)
    return choice


# ========================================
# CONFIGURAÇÃO DA SESSÃO
# ========================================


def select_session_type():
    """Pergunta se é cronômetro ou timer."""
    print("\nDeseja:")
    print("1 - Timer (tempo regressivo até zero)")
    print("2 - Cronômetro (conta crescente até parar manualmente)")

    choice = get_int_input("\nEscolha: ", 1, 2)
    return "cronometro" if choice == 2 else "timer"


def select_time():
    """Permite selecionar tempo para o timer."""
    print("\nEscolha o tempo:")
    print("1 - 15 minutos")
    print("2 - 30 minutos")
    print("3 - 45 minutos")
    print("4 - 60 minutos")
    print("5 - Definir outro tempo")

    choice = get_int_input("\nEscolha: ", 1, 5)

    time_map = {1: 15, 2: 30, 3: 45, 4: 60}

    if choice in time_map:
        return time_map[choice]
    else:
        return get_int_input("\nDigite o tempo em minutos: ", 1)


def show_summary_and_confirm(objective, session_type, minutes=None):
    """Mostra resumo e confirma início."""
    print("\n" + "-" * 40)
    print("RESUMO DA SESSÃO")
    print("-" * 40)
    print(f"Objetivo: {objective}")
    print(f"Tipo: {session_type.capitalize()}")
    if minutes:
        print(f"Tempo: {minutes} minutos")
    print("-" * 40)

    while True:
        confirm = input("\nDeseja iniciar? (s/n): ").strip().lower()
        if confirm in ["s", "n"]:
            return confirm == "s"
        print("Digite 's' para sim ou 'n' para não.")


# ========================================
# EXECUÇÃO DA SESSÃO
# ========================================


def run_stopwatch(objective):
    """Executa cronômetro (contagem crescente) em janela flutuante."""
    print("\n" + "=" * 40)
    print("CRONÔMETRO INICIADO")
    print("Uma janela flutuante foi aberta!")
    print("Clique em 'Finalizar' para parar e contabilizar o tempo.")
    print("=" * 40 + "\n")

    window = FloatingTimerWindow(is_timer=False)
    window.run()

    # Apenas salvar se o usuário clicou em "Finalizar"
    if window.saved_minutes is not None:
        minutes = window.saved_minutes
        print(f"\n{'=' * 40}")
        print("CRONÔMETRO FINALIZADO")
        print(f"Tempo total: {minutes} minutos")
        print("=" * 40)

        save_session(objective, "cronometro", minutes)
    else:
        print("\nCronômetro não finalizado. Sessão não salva.")

    input("\nPressione ENTER para continuar...")


def run_timer(objective, minutes):
    """Executa timer (contagem regressiva) em janela flutuante."""
    print("\n" + "=" * 40)
    print("TIMER INICIADO")
    print("Uma janela flutuante foi aberta!")
    print("Clique em 'Finalizar' para parar agora ou deixe terminar naturalmente.")
    print("=" * 40 + "\n")

    window = FloatingTimerWindow(is_timer=True, total_minutes=minutes)
    window.run()

    if not window.was_cancelled():
        # Se o usuário finalizou manualmente, usar os minutos registrados
        if window.saved_minutes is not None:
            recorded = window.saved_minutes
        else:
            recorded = minutes

        print(f"\n{'=' * 40}")
        print("🎉 TIMER FINALIZADO! 🎉")
        print(f"Minutos registrados: {recorded}")
        print("=" * 40)

        save_session(objective, "timer", recorded)
    else:
        print("\nTimer cancelado. Sessão não salva.")

    input("\nPressione ENTER para continuar...")


# ========================================
# HISTÓRICO
# ========================================


def show_history_menu():
    """Menu de visualização de histórico."""
    print("\n" + "=" * 40)
    print("        HISTÓRICO")
    print("=" * 40)
    print("\n1 - Diário (últimos 30 dias)")
    print("2 - Semanal (últimas 30 semanas)")
    print("3 - Mensal (últimos 12 meses)")
    print("4 - Data específica")
    print("0 - Voltar")

    choice = get_int_input("\nEscolha: ", 0, 4)

    if choice == 1:
        show_daily_history()
    elif choice == 2:
        show_weekly_history()
    elif choice == 3:
        show_monthly_history()
    elif choice == 4:
        show_specific_date_history()


def aggregate_by_date(history, date_str):
    """Agrega minutos por data específica."""
    total = 0
    for session in history:
        if session["date"] == date_str:
            total += session["minutes"]
    return total


def format_history_line(date_str, minutes):
    """Formata linha de histórico com barras."""
    hours = minutes / 60
    bars = "#" * (minutes // 10)
    return f"{date_str} = {minutes} minutos | {hours:.1f} horas | {bars}"


def show_daily_history():
    """Mostra histórico diário dos últimos 30 dias."""
    history = load_history()

    print("\n" + "=" * 40)
    print("HISTÓRICO DIÁRIO (Últimos 30 dias)")
    print("=" * 40 + "\n")

    today = datetime.now().date()
    has_data = False

    for i in range(29, -1, -1):
        date = today - timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")
        minutes = aggregate_by_date(history, date_str)

        if minutes > 0:
            print(format_history_line(date_str, minutes))
            has_data = True

    if not has_data:
        print("Nenhum dado registrado nos últimos 30 dias.")

    input("\nPressione ENTER para continuar...")


def show_weekly_history():
    """Mostra histórico semanal das últimas 30 semanas."""
    history = load_history()

    print("\n" + "=" * 40)
    print("HISTÓRICO SEMANAL (Últimas 30 semanas)")
    print("=" * 40 + "\n")

    today = datetime.now().date()
    has_data = False

    for i in range(29, -1, -1):
        week_start = today - timedelta(weeks=i, days=today.weekday())
        week_end = week_start + timedelta(days=6)

        total_minutes = 0
        for session in history:
            session_date = datetime.strptime(session["date"], "%Y-%m-%d").date()
            if week_start <= session_date <= week_end:
                total_minutes += session["minutes"]

        if total_minutes > 0:
            date_str = f"{week_start.strftime('%Y-%m-%d')} ~ {week_end.strftime('%Y-%m-%d')}"
            hours = total_minutes / 60
            bars = "#" * (total_minutes // 10)
            print(f"{date_str} = {total_minutes} minutos | {hours:.1f} horas | {bars}")
            has_data = True

    if not has_data:
        print("Nenhum dado registrado nas últimas 30 semanas.")

    input("\nPressione ENTER para continuar...")


def show_monthly_history():
    """Mostra histórico mensal dos últimos 12 meses."""
    history = load_history()

    print("\n" + "=" * 40)
    print("HISTÓRICO MENSAL (Últimos 12 meses)")
    print("=" * 40 + "\n")

    today = datetime.now().date()
    has_data = False

    for i in range(11, -1, -1):
        month_date = today.replace(day=1) - timedelta(days=i * 30)
        year = month_date.year
        month = month_date.month

        total_minutes = 0
        for session in history:
            session_date = datetime.strptime(session["date"], "%Y-%m-%d").date()
            if session_date.year == year and session_date.month == month:
                total_minutes += session["minutes"]

        if total_minutes > 0:
            date_str = f"{year}-{month:02d}"
            hours = total_minutes / 60
            bars = "#" * (total_minutes // 10)
            print(f"{date_str} = {total_minutes} minutos | {hours:.1f} horas | {bars}")
            has_data = True

    if not has_data:
        print("Nenhum dado registrado nos últimos 12 meses.")

    input("\nPressione ENTER para continuar...")


def show_specific_date_history():
    """Mostra histórico de uma data específica."""
    history = load_history()

    while True:
        date_input = input("\nDigite a data (DD/MM/YYYY): ").strip()

        try:
            date_obj = datetime.strptime(date_input, "%d/%m/%Y")
            date_str = date_obj.strftime("%Y-%m-%d")
            break
        except ValueError:
            print("Formato inválido. Use DD/MM/YYYY (exemplo: 16/02/2026)")

    minutes = aggregate_by_date(history, date_str)

    print("\n" + "=" * 40)
    print(f"HISTÓRICO DE {date_input}")
    print("=" * 40 + "\n")

    if minutes > 0:
        print(format_history_line(date_str, minutes))
    else:
        print(f"Nenhum dado registrado em {date_input}.")

    input("\nPressione ENTER para continuar...")


# ========================================
# FLUXO PRINCIPAL
# ========================================


def start_session(objective_name):
    """Inicia uma sessão de pomodoro."""
    session_type = select_session_type()

    minutes = None
    if session_type == "timer":
        minutes = select_time()

    if not show_summary_and_confirm(objective_name, session_type, minutes):
        print("\nSessão cancelada.")
        time.sleep(1)
        return

    if session_type == "cronometro":
        run_stopwatch(objective_name)
    else:
        run_timer(objective_name, minutes)


def main():
    """Função principal do programa."""
    objective_map = {1: "Estudar", 2: "Trabalhar", 3: "Outros"}

    while True:
        clear_screen()
        choice = show_main_menu()

        if choice == 0:
            print("\nAté logo! 👋")
            break
        elif choice in [1, 2, 3]:
            start_session(objective_map[choice])
        elif choice == 4:
            show_history_menu()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nPrograma encerrado pelo usuário.")
        sys.exit(0)
