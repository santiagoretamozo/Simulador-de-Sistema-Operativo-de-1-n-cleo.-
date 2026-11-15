import csv
import sys
import os

MEMORIA_TOTAL = 1024
SO_RESERVADO = 100
MAX_MULTIPROGRAMACION = 5

def limpiar_pantalla():
    os.system("cls" if sys.platform.startswith("win") else "clear")

def crear_pcb(id_proceso, tamano, llegada, irrupcion):
    tamano = int(tamano)
    if tamano > (MEMORIA_TOTAL - SO_RESERVADO):
        raise ValueError(f"Proceso {id_proceso} supera la memoria disponible.")
    return {
        "id": str(id_proceso),
        "tamano": tamano,
        "llegada": int(llegada),
        "irrupcion_total": int(irrupcion),
        "tiempo_restante": int(irrupcion),
        "estado": "Nuevo",
        "tiempo_espera": 0,
        "tiempo_retorno": 0,
        "tiempo_inicio": -1,
        "tiempo_fin": -1,
        "particion": -1
    }

def cargar_procesos(archivo):
    with open(archivo, mode="r", encoding="utf-8-sig", newline="") as f:
        return [crear_pcb(r["ID"].strip(), r["Tamano"].strip(), r["Llegada"].strip(), r["Irrupcion"].strip()) for r in csv.DictReader(f)]

def inicializar_memoria():
    return [
        {"id_particion": 0, "inicio": 0, "tamano": SO_RESERVADO, "libre": False, "proceso": "SO"},
        {"id_particion": 1, "inicio": SO_RESERVADO, "tamano": MEMORIA_TOTAL - SO_RESERVADO, "libre": True, "proceso": None}
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
    idx = buscar_best_fit(mem, proc["tamano"])
    if idx == -1:
        return False
    p = mem[idx]
    if p["tamano"] == proc["tamano"]:
        p["libre"] = False
        p["proceso"] = proc["id"]
        proc["particion"] = p["id_particion"]
    else:
        nueva_oc = {
            "id_particion": p["id_particion"],
            "inicio": p["inicio"],
            "tamano": proc["tamano"],
            "libre": False,
            "proceso": proc["id"]
        }
        nueva_li = {
            "id_particion": p["id_particion"] + 1,
            "inicio": p["inicio"] + proc["tamano"],
            "tamano": p["tamano"] - proc["tamano"],
            "libre": True,
            "proceso": None
        }
        mem[idx] = nueva_oc
        mem.insert(idx + 1, nueva_li)
        actualizar_ids(mem)
        proc["particion"] = nueva_oc["id_particion"]
    return True

def liberar_memoria(mem, proc):
    for p in mem:
        if p["proceso"] == proc["id"]:
            p["libre"] = True
            p["proceso"] = None
            break
    proc["particion"] = -1

    # Fusión de huecos libres contiguos (sin compactación)
    i = 0
    while i < len(mem) - 1:
        if mem[i]["libre"] and mem[i+1]["libre"]:
            mem[i]["tamano"] += mem[i+1]["tamano"]
            mem.pop(i + 1)
        else:
            i += 1
    actualizar_ids(mem)

def contar_activos(procs):
    return sum(1 for p in procs if p["estado"] in ("Listo", "Listo/Suspendido", "Ejecutando"))

def mostrar_estado(reloj, eventos, procs, mem):
    limpiar_pantalla()
    print(f"=====================================================")
    print(f" RELOJ DEL SISTEMA: Ciclo [{reloj}] — EVENTO DETECTADO")
    print(f"=====================================================")

    print("\n--- Eventos Ocurridos ---")
    for ev in eventos:
        print(f"  > {ev}")

    print("\n--- Tabla de Procesos (PCB) ---")
    print(f"{'ID':<5} | {'ESTADO':<18} | {'TAM':<5} | {'TR':<5} | {'PART':<5} | {'ESPERA':<7} | {'RETORNO':<7}")
    print("-" * 65)
    for p in procs:
        ret = p["tiempo_retorno"] if p["tiempo_retorno"] != 0 else "-"
        print(f"{p['id']:<5} | {p['estado']:<18} | {p['tamano']:<5} | {p['tiempo_restante']:<5} | {p['particion']:<5} | {p['tiempo_espera']:<7} | {str(ret):<7}")

    print("\n--- Tabla de Particiones de Memoria ---")
    print(f"{'ID':<5} | {'INICIO':<8} | {'TAMAÑO':<8} | {'ESTADO':<10} | {'PROCESO':<8}")
    print("-" * 55)
    for m in mem:
        proc_str = str(m["proceso"]) if m["proceso"] else "-"
        print(f"{m['id_particion']:<5} | {m['inicio']:<8} | {m['tamano']:<8} | {'Libre' if m['libre'] else 'Ocupada':<10} | {proc_str:<8}")
    print("=" * 65)

def ejecutar_simulacion(archivo):
    try:
        procs = cargar_procesos(archivo)
    except Exception as e:
        print(f"[ERROR] No se pudo leer el archivo: {e}")
        input("\nPresiona Enter para continuar...")
        return

    mem = inicializar_memoria()
    reloj = 0

    print(f"\n[INFO] Simulación iniciada con {len(procs)} procesos. Modo Event-Driven activo.")
    input("Presiona Enter para comenzar...")

    while not all(p["estado"] == "Terminado" for p in procs):
        eventos = []

        # 1. Planificador de Largo Plazo (LP)
        activos = contar_activos(procs)
        for p in procs:
            if p["estado"] == "Nuevo" and p["llegada"] <= reloj:
                if activos >= MAX_MULTIPROGRAMACION:
                    eventos.append(f"{p['id']} no admitido (límite de multiprogramación alcanzado)")
                elif asignar_memoria(mem, p):
                    p["estado"] = "Listo"
                    eventos.append(f"{p['id']}: Nuevo -> Listo (Memoria asignada con Best Fit)")
                    activos += 1
                else:
                    p["estado"] = "Listo/Suspendido"
                    eventos.append(f"{p['id']}: Nuevo -> Listo/Suspendido (Sin memoria disponible)")
                    activos += 1

        # 2. Planificador de Mediano Plazo (MP) - Reactivación
        suspendidos = sorted([x for x in procs if x["estado"] == "Listo/Suspendido"], key=lambda x: x["tiempo_restante"])
        for p in suspendidos:
            if asignar_memoria(mem, p):
                p["estado"] = "Listo"
                eventos.append(f"{p['id']}: Listo/Suspendido -> Listo (Reactivado en memoria)")
                break

        # 3. Actualizar tiempos de espera
        for p in procs:
            if p["estado"] in ("Listo", "Listo/Suspendido"):
                p["tiempo_espera"] += 1

        # 4. Planificador de Corto Plazo (SRTF) y CPU
        ejecutando = next((p for p in procs if p["estado"] == "Ejecutando"), None)
        candidato = min([p for p in procs if p["estado"] == "Listo"], key=lambda x: x["tiempo_restante"], default=None)

        if ejecutando is None and candidato:
            candidato["estado"] = "Ejecutando"
            if candidato["tiempo_inicio"] == -1:
                candidato["tiempo_inicio"] = reloj
            eventos.append(f"{candidato['id']} ingresa a CPU")
            ejecutando = candidato
        elif ejecutando and candidato and candidato["tiempo_restante"] < ejecutando["tiempo_restante"]:
            eventos.append(f"EXPROPIACIÓN: {ejecutando['id']} (TR={ejecutando['tiempo_restante']}) -> {candidato['id']} (TR={candidato['tiempo_restante']})")
            ejecutando["estado"] = "Listo"
            candidato["estado"] = "Ejecutando"
            ejecutando = candidato

        # 5. Ejecución del ciclo en CPU
        if ejecutando:
            if ejecutando["tiempo_inicio"] == -1:
                ejecutando["tiempo_inicio"] = reloj
            ejecutando["tiempo_restante"] -= 1

            if ejecutando["tiempo_restante"] == 0:
                ejecutando["tiempo_fin"] = reloj + 1
                ejecutando["tiempo_retorno"] = ejecutando["tiempo_fin"] - ejecutando["llegada"]
                liberar_memoria(mem, ejecutando)
                ejecutando["estado"] = "Terminado"
                eventos.append(f"{ejecutando['id']} finalizó su ejecución y liberó memoria.")

        # --- ENFOQUE DIRIGIDO POR EVENTOS ---
        # Solo se pausa y muestra pantalla si hubo eventos relevantes en este ciclo
        if eventos:
            mostrar_estado(reloj, eventos, procs, mem)
            op = input("\n[Presiona Enter para siguiente evento / Escribe 'q' para salir]: ")
            if op.lower() == 'q':
                break

        reloj += 1

    # Estadísticas finales
    limpiar_pantalla()
    print("\n" + "=" * 55)
    print("          SIMULACIÓN FINALIZADA — ESTADÍSTICAS")
    print("=" * 55)
    total_procs = len(procs)
    t_esp = sum(p["tiempo_espera"] for p in procs) / total_procs
    t_ret = sum(p["tiempo_retorno"] for p in procs) / total_procs
    print(f"  Tiempo total del sistema   : {reloj} ciclos")
    print(f"  Procesos procesados        : {total_procs}")
    print(f"  Tiempo de espera promedio  : {t_esp:.2f} ciclos")
    print(f"  Tiempo de retorno promedio : {t_ret:.2f} ciclos")
    print("=" * 55)
    input("\nPresiona Enter para volver al menú principal...")

def main():
    if not os.path.exists("procesos.csv"):
        with open("procesos.csv", "w", encoding="utf-8") as f:
            f.write("ID,Tamano,Llegada,Irrupcion\nP1,120,0,5\nP2,250,1,8\nP3,80,2,3\nP4,300,3,6\nP5,150,4,4\n")

    while True:
        limpiar_pantalla()
        print("=====================================================")
        print("      SIMULADOR DE PLANIFICACIÓN Y MEMORIA")
        print("=====================================================")
        print(" 1. Cargar 'procesos.csv' y ejecutar simulación")
        print(" 2. Salir")
        print("=====================================================")
        op = input("\nSelecciona una opción (1-2): ").strip()
        if op == "1":
            ejecutar_simulacion("procesos.csv")
        elif op == "2":
            print("\n¡Gracias por utilizar el simulador!")
            break
        else:
            input("\n[ERROR] Opción inválida. Presiona Enter...")

if __name__ == "__main__":
    main()