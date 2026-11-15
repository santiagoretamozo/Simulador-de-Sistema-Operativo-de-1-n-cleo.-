import csv
import os
import sys
import unicodedata

# ---- Parámetros de la consigna -------------------------------------------------
SO_RESERVADO = 100            # K destinados al Sistema Operativo
MEMORIA_USUARIO = 450         # K para trabajos de usuario
MEMORIA_TOTAL = SO_RESERVADO + MEMORIA_USUARIO
MAX_MULTIPROGRAMACION = 5     # Ejecución + Listos + Listos/Suspendidos
MAX_PROCESOS = 10             # máximo de procesos por simulación

ESTADOS_ACTIVOS = ("Listo", "Listo/Suspendido", "Ejecutando")

# Nombres de columna aceptados (se comparan sin tildes, mayúsculas ni símbolos).
# Soporta tanto "ID,Tamano,Llegada,Irrupcion" como "Proceso,TA,TI,Tamaño (K)".
CAMPOS = {
    "id": {"id", "proceso", "pid"},
    "tamano": {"tamano", "tamanok", "tam"},
    "llegada": {"llegada", "ta"},
    "irrupcion": {"irrupcion", "ti"},
}

PROMPT_COMENZAR = "Presiona Enter para comenzar..."
PROMPT_EVENTO = "[Enter = siguiente evento | q = salir]: "
PROMPT_VOLVER = "Presiona Enter para volver al menú principal..."


class ProcesoRechazado(ValueError):
    """Proceso que no puede entrar en la simulación (tamaño o cupo)."""


def limpiar_pantalla():
    os.system("cls" if sys.platform.startswith("win") else "clear")


# ---------------------------------------------------------------- carga de datos
def _normalizar(texto):
    t = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return "".join(c for c in t.lower() if c.isalnum())


def mapear_columnas(encabezados):
    mapa = {}
    for original in encabezados or []:
        n = _normalizar(original)
        for campo, alias in CAMPOS.items():
            if n in alias and campo not in mapa:
                mapa[campo] = original
    faltan = [c for c in CAMPOS if c not in mapa]
    if faltan:
        raise ValueError(f"faltan las columnas {faltan}. Encabezados encontrados: {list(encabezados or [])}")
    return mapa


def _entero(valor, nombre):
    try:
        return int(valor)
    except (TypeError, ValueError):
        raise ValueError(f"'{nombre}' debe ser un entero (se recibió '{valor}')")


def crear_pcb(id_proceso, tamano, llegada, irrupcion, memoria_total=MEMORIA_TOTAL):
    tamano = _entero(tamano, "tamaño")
    llegada = _entero(llegada, "llegada")
    irrupcion = _entero(irrupcion, "irrupción")
    if not str(id_proceso).strip():
        raise ValueError("el proceso no tiene ID")
    if tamano <= 0 or llegada < 0 or irrupcion <= 0:
        raise ValueError(f"proceso {id_proceso}: tamaño e irrupción deben ser > 0 y llegada >= 0")
    disponible = memoria_total - SO_RESERVADO
    if tamano > disponible:
        raise ProcesoRechazado(f"Proceso {id_proceso} ({tamano}K) supera la memoria disponible ({disponible}K).")
    return {
        "id": str(id_proceso).strip(),
        "tamano": tamano,
        "llegada": llegada,
        "irrupcion_total": irrupcion,
        "tiempo_restante": irrupcion,
        "estado": "Nuevo",
        "tiempo_espera": 0,
        "tiempo_retorno": 0,
        "tiempo_inicio": -1,
        "tiempo_fin": -1,
        "particion": -1,
        "avisado": False,  # para no repetir el aviso de "no admitido"
    }


def cargar_procesos(archivo, memoria_total=MEMORIA_TOTAL):
    """Devuelve (procesos, descartados). Descartados: no caben nunca en memoria o exceden el máximo."""
    procs, descartados, ids = [], [], set()
    with open(archivo, mode="r", encoding="utf-8-sig", newline="") as f:
        lector = csv.DictReader(f)
        mapa = mapear_columnas(lector.fieldnames)
        for nro, fila in enumerate(lector, start=2):
            vals = {campo: (fila.get(col) or "").strip() for campo, col in mapa.items()}
            if not any(vals.values()):
                continue  # línea en blanco
            try:
                pcb = crear_pcb(vals["id"], vals["tamano"], vals["llegada"], vals["irrupcion"], memoria_total)
            except ProcesoRechazado as e:
                descartados.append(str(e))
                continue
            except ValueError as e:
                raise ValueError(f"fila {nro}: {e}")
            if pcb["id"] in ids:
                raise ValueError(f"fila {nro}: ID duplicado '{pcb['id']}'")
            if len(procs) >= MAX_PROCESOS:
                descartados.append(f"Proceso {pcb['id']} excede el máximo de {MAX_PROCESOS} procesos.")
                continue
            ids.add(pcb["id"])
            procs.append(pcb)
    return procs, descartados


def cargar_manual(memoria_total=MEMORIA_TOTAL):
    """Carga de procesos por parte del usuario (máximo MAX_PROCESOS)."""
    procs, ids = [], set()
    print(f"\nCarga manual de procesos (máximo {MAX_PROCESOS}). Deja el ID vacío para terminar.")
    while len(procs) < MAX_PROCESOS:
        pid = input(f"\nID del proceso #{len(procs) + 1}: ").strip()
        if not pid:
            break
        if pid in ids:
            print("[ERROR] Ese ID ya fue cargado.")
            continue
        try:
            tam = input("  Tamaño (K)          : ").strip()
            llegada = input("  Tiempo de arribo    : ").strip()
            irrup = input("  Tiempo de irrupción : ").strip()
            pcb = crear_pcb(pid, tam, llegada, irrup, memoria_total)
        except ProcesoRechazado as e:
            print(f"[AVISO] {e} No se agrega.")
            continue
        except ValueError as e:
            print(f"[ERROR] {e}")
            continue
        ids.add(pcb["id"])
        procs.append(pcb)
    if len(procs) == MAX_PROCESOS:
        print(f"\n[INFO] Se alcanzó el máximo de {MAX_PROCESOS} procesos.")
    return procs


# ---------------------------------------------------------------------- memoria
def inicializar_memoria(memoria_total=MEMORIA_TOTAL):
    return [
        {"id_particion": 0, "inicio": 0, "tamano": SO_RESERVADO, "libre": False, "proceso": "SO"},
        {"id_particion": 1, "inicio": SO_RESERVADO, "tamano": memoria_total - SO_RESERVADO, "libre": True, "proceso": None},
    ]


def actualizar_ids(mem):
    for i, p in enumerate(mem):
        p["id_particion"] = i


def buscar_best_fit(mem, tamano_proceso):
    idx, mejor_dif = -1, float("inf")
    for i, p in enumerate(mem):
        if p["libre"] and p["tamano"] >= tamano_proceso:
            dif = p["tamano"] - tamano_proceso
            if dif < mejor_dif:
                mejor_dif, idx = dif, i
    return idx


def asignar_memoria(mem, proc):
    """MVT: la partición se crea con el tamaño exacto del proceso (fragmentación interna = 0)."""
    idx = buscar_best_fit(mem, proc["tamano"])
    if idx == -1:
        return False
    p = mem[idx]
    if p["tamano"] == proc["tamano"]:
        p["libre"] = False
        p["proceso"] = proc["id"]
    else:
        nueva_oc = {
            "id_particion": p["id_particion"],
            "inicio": p["inicio"],
            "tamano": proc["tamano"],
            "libre": False,
            "proceso": proc["id"],
        }
        nueva_li = {
            "id_particion": p["id_particion"] + 1,
            "inicio": p["inicio"] + proc["tamano"],
            "tamano": p["tamano"] - proc["tamano"],
            "libre": True,
            "proceso": None,
        }
        mem[idx] = nueva_oc
        mem.insert(idx + 1, nueva_li)
        actualizar_ids(mem)
    return True


def liberar_memoria(mem, proc):
    for p in mem:
        if p["proceso"] == proc["id"]:
            p["libre"] = True
            p["proceso"] = None
            break

    # Fusión de huecos libres contiguos (sin compactación)
    i = 0
    while i < len(mem) - 1:
        if mem[i]["libre"] and mem[i + 1]["libre"]:
            mem[i]["tamano"] += mem[i + 1]["tamano"]
            mem.pop(i + 1)
        else:
            i += 1
    actualizar_ids(mem)


def fragmentacion_interna(particion, procs):
    """Partición ocupada por un proceso: tamaño de partición - tamaño del proceso. Libre: no aplica."""
    if particion["libre"]:
        return None
    if particion["proceso"] == "SO":
        return 0
    proc = next((p for p in procs if p["id"] == particion["proceso"]), None)
    return particion["tamano"] - proc["tamano"] if proc else 0


def sincronizar_particiones(procs, mem):
    """Los ids de partición se renumeran al insertar/fusionar huecos: se recalculan desde la memoria."""
    ubicacion = {m["proceso"]: m["id_particion"] for m in mem if m["proceso"]}
    for p in procs:
        p["particion"] = ubicacion.get(p["id"], -1)


def contar_activos(procs):
    return sum(1 for p in procs if p["estado"] in ESTADOS_ACTIVOS)


# ------------------------------------------------------------------ simulación
def planificar(reloj, procs, mem):
    """Todo lo que ocurre en el INSTANTE `reloj`, antes de que la CPU ejecute el ciclo.

    Devuelve (eventos, relevante). `relevante` es True si en este instante llegó un
    proceso nuevo o terminó el que estaba en ejecución: solo entonces se presenta la salida.
    """
    eventos = []
    relevante = False

    # A. Terminación del proceso en ejecución (agotó su irrupción en el ciclo anterior)
    ej = next((p for p in procs if p["estado"] == "Ejecutando"), None)
    if ej and ej["tiempo_restante"] == 0:
        ej["tiempo_fin"] = reloj
        ej["tiempo_retorno"] = reloj - ej["llegada"]
        liberar_memoria(mem, ej)
        ej["estado"] = "Terminado"
        eventos.append(f"{ej['id']} terminó y liberó su partición.")
        relevante = True

    # B. Planificador de Mediano Plazo: reactivar suspendidos (los más cortos primero).
    #    Va antes que el LP para que un proceso nuevo no les quite el lugar en memoria.
    suspendidos = sorted(
        (p for p in procs if p["estado"] == "Listo/Suspendido"),
        key=lambda x: (x["tiempo_restante"], x["llegada"]),
    )
    for p in suspendidos:
        if asignar_memoria(mem, p):
            p["estado"] = "Listo"
            eventos.append(f"{p['id']}: Listo/Suspendido -> Listo (reactivado en memoria)")

    # C. Planificador de Largo Plazo: admisión de procesos que ya llegaron
    activos = contar_activos(procs)
    for p in sorted(procs, key=lambda x: x["llegada"]):  # por orden de arribo (estable: respeta el archivo en empates)
        if p["estado"] == "Nuevo" and p["llegada"] <= reloj:
            if p["llegada"] == reloj:
                eventos.append(f"Arribo de {p['id']} (tamaño {p['tamano']}K, irrupción {p['irrupcion_total']})")
                relevante = True
            if activos >= MAX_MULTIPROGRAMACION:
                if not p["avisado"]:  # se avisa una sola vez, no en cada instante
                    p["avisado"] = True
                    eventos.append(f"{p['id']} queda en Nuevo (límite de {MAX_MULTIPROGRAMACION} procesos alcanzado)")
            elif asignar_memoria(mem, p):
                p["estado"] = "Listo"
                eventos.append(f"{p['id']}: Nuevo -> Listo (memoria asignada con Best-Fit)")
                activos += 1
            else:
                p["estado"] = "Listo/Suspendido"
                eventos.append(f"{p['id']}: Nuevo -> Listo/Suspendido (sin memoria disponible)")
                activos += 1

    # D. Planificador de Corto Plazo (SRTF, con expropiación)
    ej = next((p for p in procs if p["estado"] == "Ejecutando"), None)
    candidato = min(
        (p for p in procs if p["estado"] == "Listo"),
        key=lambda x: (x["tiempo_restante"], x["llegada"]),
        default=None,
    )
    if ej is None and candidato:
        candidato["estado"] = "Ejecutando"
        eventos.append(f"{candidato['id']} ingresa a CPU")
    elif ej and candidato and candidato["tiempo_restante"] < ej["tiempo_restante"]:
        eventos.append(
            f"EXPROPIACIÓN: {ej['id']} (TR={ej['tiempo_restante']}) "
            f"-> {candidato['id']} (TR={candidato['tiempo_restante']})"
        )
        ej["estado"] = "Listo"
        candidato["estado"] = "Ejecutando"

    sincronizar_particiones(procs, mem)
    return eventos, relevante


def ejecutar_ciclo(reloj, procs):
    """La CPU ejecuta el ciclo [reloj, reloj+1) y se acumula la espera de los demás."""
    ej = next((p for p in procs if p["estado"] == "Ejecutando"), None)
    if ej:
        if ej["tiempo_inicio"] == -1:
            ej["tiempo_inicio"] = reloj
        ej["tiempo_restante"] -= 1

    # Espera: proceso que ya llegó, no terminó y no usó la CPU en este ciclo
    # (incluye los que esperan admisión o están suspendidos). Así: espera = retorno - irrupción.
    for p in procs:
        if p["llegada"] <= reloj and p["estado"] not in ("Terminado", "Ejecutando"):
            p["tiempo_espera"] += 1


# ------------------------------------------------------------------ salida
def _cola(procs, estado):
    cola = sorted((p for p in procs if p["estado"] == estado), key=lambda x: (x["tiempo_restante"], x["llegada"]))
    return ", ".join(f"{p['id']}(TR={p['tiempo_restante']})" for p in cola) or "(vacía)"


def mostrar_estado(reloj, eventos, procs, mem, limpiar=limpiar_pantalla):
    limpiar()
    print("=" * 70)
    print(f" INSTANTE DE SIMULACIÓN: t = {reloj}")
    print("=" * 70)

    print("\n--- Eventos ---")
    for t, ev in eventos:
        print(f"  [t={t}] {ev}")

    ej = next((p for p in procs if p["estado"] == "Ejecutando"), None)
    print("\n--- Estado del procesador ---")
    if ej:
        print(f"  Ejecutando: {ej['id']}  (restante {ej['tiempo_restante']} de {ej['irrupcion_total']})")
    else:
        print("  Ocioso (ningún proceso en ejecución)")

    print("\n--- Tabla de particiones de memoria ---")
    print(f"{'ID':<4} | {'COMIENZO':<9} | {'TAMAÑO':<7} | {'PROCESO':<8} | {'FRAG. INTERNA':<13}")
    print("-" * 52)
    for m in mem:
        frag = fragmentacion_interna(m, procs)
        proc_str = m["proceso"] if m["proceso"] else "(libre)"
        print(f"{m['id_particion']:<4} | {m['inicio']:<9} | {m['tamano']:<7} | {proc_str:<8} | {'-' if frag is None else frag:<13}")

    print("\n--- Colas ---")
    print(f"  Listos (orden SRTF)       : {_cola(procs, 'Listo')}")
    print(f"  Listos/Suspendidos        : {_cola(procs, 'Listo/Suspendido')}")
    nuevos = [p["id"] for p in procs if p["estado"] == "Nuevo" and p["llegada"] <= reloj]
    if nuevos:
        print(f"  Nuevos esperando admisión : {', '.join(nuevos)}")

    print("\n--- Tabla de procesos ---")
    print(f"{'ID':<5} | {'ESTADO':<17} | {'TAM':<5} | {'TR':<4} | {'PART':<5} | {'ESPERA':<7} | {'RETORNO':<7}")
    print("-" * 66)
    for p in procs:
        ret = p["tiempo_retorno"] if p["estado"] == "Terminado" else "-"
        part = p["particion"] if p["particion"] != -1 else "-"
        print(f"{p['id']:<5} | {p['estado']:<17} | {p['tamano']:<5} | {p['tiempo_restante']:<4} | {part:<5} | {p['tiempo_espera']:<7} | {str(ret):<7}")
    print("=" * 70)


def mostrar_estadisticas(procs, reloj, interrumpida):
    terminados = [p for p in procs if p["estado"] == "Terminado"]
    print("\n" + "=" * 66)
    titulo = "SIMULACIÓN INTERRUMPIDA — INFORME PARCIAL" if interrumpida else "SIMULACIÓN FINALIZADA — INFORME ESTADÍSTICO"
    print(f"{titulo:^66}")
    print("=" * 66)
    print(f"{'ID':<5} | {'ARRIBO':<7} | {'IRRUP.':<7} | {'FIN':<5} | {'RETORNO':<8} | {'ESPERA':<7}")
    print("-" * 56)
    for p in terminados:
        print(f"{p['id']:<5} | {p['llegada']:<7} | {p['irrupcion_total']:<7} | {p['tiempo_fin']:<5} | {p['tiempo_retorno']:<8} | {p['tiempo_espera']:<7}")
    print("-" * 56)
    print(f"  Tiempo total de simulación  : {reloj} unidades")
    print(f"  Procesos terminados         : {len(terminados)} de {len(procs)}")
    if terminados:
        t_esp = sum(p["tiempo_espera"] for p in terminados) / len(terminados)
        t_ret = sum(p["tiempo_retorno"] for p in terminados) / len(terminados)
        print(f"  Tiempo de retorno promedio  : {t_ret:.2f}")
        print(f"  Tiempo de espera promedio   : {t_esp:.2f}")
    if reloj > 0:
        print(f"  Rendimiento del sistema     : {len(terminados) / reloj:.4f} trabajos terminados por unidad de tiempo")
    print("=" * 66)


def simular(procs, descartados=(), memoria_total=MEMORIA_TOTAL, pausar=input, limpiar=limpiar_pantalla):
    """Corre la simulación. `pausar` y `limpiar` son inyectables (los usan los tests)."""
    for aviso in descartados:
        print(f"[AVISO] {aviso} Proceso descartado.")
    if not procs:
        print("[ERROR] No hay procesos válidos para simular.")
        pausar("\nPresiona Enter para continuar...")
        return None

    mem = inicializar_memoria(memoria_total)
    reloj = 0
    interrumpida = False
    pendientes = []  # eventos no presentados todavía (p. ej. expropiaciones)
    limite = max(p["llegada"] for p in procs) + sum(p["irrupcion_total"] for p in procs) + 1

    print(f"\n[INFO] Simulación iniciada con {len(procs)} procesos "
          f"({memoria_total - SO_RESERVADO}K de memoria de usuario).")
    pausar(PROMPT_COMENZAR)

    while True:
        if reloj > limite:  # seguro contra bucles infinitos
            print(f"[ERROR] La simulación no converge (t={reloj}). Se interrumpe.")
            interrumpida = True
            break

        eventos, relevante = planificar(reloj, procs, mem)
        pendientes.extend((reloj, e) for e in eventos)
        todos = all(p["estado"] == "Terminado" for p in procs)

        # Salida solo cuando llega un proceso nuevo o termina el que estaba en ejecución
        if relevante:
            mostrar_estado(reloj, pendientes, procs, mem, limpiar)
            pendientes = []
            op = pausar(PROMPT_EVENTO)
            if not todos and str(op).strip().lower() == "q":
                interrumpida = True
                break
        if todos:
            break

        ejecutar_ciclo(reloj, procs)
        reloj += 1

    limpiar()
    mostrar_estadisticas(procs, reloj, interrumpida)
    pausar("\n" + PROMPT_VOLVER)
    return procs, reloj


def ejecutar_simulacion(archivo, memoria_total=MEMORIA_TOTAL, pausar=input, limpiar=limpiar_pantalla):
    try:
        procs, descartados = cargar_procesos(archivo, memoria_total)
    except (OSError, ValueError) as e:
        print(f"[ERROR] No se pudo leer el archivo: {e}")
        pausar("\nPresiona Enter para continuar...")
        return None
    return simular(procs, descartados, memoria_total, pausar, limpiar)


def main():
    args = sys.argv[1:]
    # Uso directo: python main.py lote1.csv
    if args:
        for a in args:
            ejecutar_simulacion(a)
        return

    while True:
        limpiar_pantalla()
        print("=====================================================")
        print("      SIMULADOR DE PLANIFICACIÓN Y MEMORIA (MVT)")
        print("=====================================================")
        print(f" Memoria: {SO_RESERVADO}K SO + {MEMORIA_USUARIO}K usuario | Best-Fit | SRTF")
        print("-----------------------------------------------------")
        print(" 1. Cargar procesos desde un archivo CSV")
        print(" 2. Cargar procesos manualmente")
        print(" 3. Salir")
        print("=====================================================")
        op = input("\nSelecciona una opción (1-3): ").strip()
        if op == "1":
            nombre = input("Archivo CSV [procesos.csv]: ").strip() or "procesos.csv"
            ejecutar_simulacion(nombre)
        elif op == "2":
            simular(cargar_manual())
        elif op == "3":
            print("\n¡Gracias por utilizar el simulador!")
            break
        else:
            input("\n[ERROR] Opción inválida. Presiona Enter...")


if __name__ == "__main__":
    main()
