import csv
import os

# ------------------------- Constantes del Sistema -------------------------
MEM_SO = 100        # Memoria reservada para el Sistema Operativo (100K)
MEM_USUARIO = 450   # Memoria disponible para procesos de usuario (450K)
MAX_PROCESOS = 10   # Límite máximo de procesos admitidos por simulación
MAX_MULTI = 5       # Grado máximo de multiprogramación (Ejecución + Listos + Listos/Suspendidos)


def limpiar_pantalla():
    """Limpia la consola según el sistema operativo."""
    os.system("cls" if os.name == "nt" else "clear")


def validar(id_proc, tam, llegada, irrup, procs):
    """Valida las restricciones de negocio y memoria para un proceso."""
    if tam <= 0 or llegada < 0 or irrup <= 0:
        return f"{id_proc}: tamaño e irrupción deben ser > 0 y arribo >= 0."
    if tam > MEM_USUARIO:
        return f"{id_proc} ({tam}K) excede la memoria de usuario disponible ({MEM_USUARIO}K)."
    if any(p["id"] == id_proc for p in procs):
        return f"ID repetido '{id_proc}'."
    if len(procs) >= MAX_PROCESOS:
        return f"Máximo de {MAX_PROCESOS} procesos alcanzado."
    return ""


def leer_archivo(nombre):
    """Lee un archivo CSV con columnas: Proceso, TA, TI, Tamaño (K)."""
    procs = []
    try:
        with open(nombre, encoding="utf-8-sig") as archivo:
            lector = csv.reader(archivo)
            next(lector, None)  # Ignora la fila de encabezados
            for fila in lector:
                if len(fila) < 4:
                    continue
                try:
                    pid, llegada, irrup, tam = fila[0].strip(), int(fila[1]), int(fila[2]), int(fila[3])
                except ValueError:
                    print(f"[AVISO] Fila con datos no numéricos ignorada: {fila}")
                    continue

                err = validar(pid, tam, llegada, irrup, procs)
                if not err:
                    procs.append({
                        "id": pid,
                        "tam": tam,
                        "llegada": llegada,
                        "irrup": irrup,
                        "restante": irrup,
                        "estado": "Nuevo",
                        "fin": 0
                    })
                else:
                    print(f"[AVISO] {err} ({pid} descartado)")
    except OSError:
        print("[ERROR] No se pudo abrir el archivo. Verifica el nombre o la ruta.")
    return sorted(procs, key=lambda p: p["llegada"])


def cargar_manual():
    """Permite el ingreso interactivo de procesos por teclado."""
    procs = []
    print(f"\nCarga manual (máx {MAX_PROCESOS}). Deja el ID vacío para terminar.")
    while len(procs) < MAX_PROCESOS:
        pid = input(f"\nID del proceso {len(procs) + 1}: ").strip()
        if not pid:
            break
        try:
            tam = int(input("  Tamaño (K): "))
            llegada = int(input("  Tiempo de arribo: "))
            irrup = int(input("  Tiempo de irrupción: "))
        except ValueError:
            print("[ERROR] Debes ingresar números enteros.")
            continue

        err = validar(pid, tam, llegada, irrup, procs)
        if err:
            print(f"[ERROR] {err}")
        else:
            procs.append({
                "id": pid,
                "tam": tam,
                "llegada": llegada,
                "irrup": irrup,
                "restante": irrup,
                "estado": "Nuevo",
                "fin": 0
            })
    return sorted(procs, key=lambda p: p["llegada"])


def crear_memoria():
    """Inicializa la memoria principal con la partición fija del SO y un bloque libre de usuario."""
    return [
        {"inicio": 0, "tam": MEM_SO, "proc": "SO"},
        {"inicio": MEM_SO, "tam": MEM_USUARIO, "proc": None}
    ]


def asignar_best_fit(memoria, proc):
    """
    Asigna memoria dinámica (MVT) usando el algoritmo Best-Fit (Mejor Ajuste).
    Busca el hueco libre más pequeño donde quepa el proceso y divide la partición si sobra espacio.
    """
    mejor = min(
        (i for i, p in enumerate(memoria) if p["proc"] is None and p["tam"] >= proc["tam"]),
        key=lambda i: memoria[i]["tam"],
        default=-1
    )
    if mejor == -1:
        return False

    hueco = memoria[mejor]
    if hueco["tam"] > proc["tam"]:
        memoria.insert(mejor + 1, {
            "inicio": hueco["inicio"] + proc["tam"],
            "tam": hueco["tam"] - proc["tam"],
            "proc": None
        })
    hueco["tam"], hueco["proc"] = proc["tam"], proc["id"]
    return True


def liberar(memoria, id_proc):
    """Libera la partición ocupada por el proceso y compacta huecos libres adyacentes (coalescing)."""
    for p in memoria:
        if p["proc"] == id_proc:
            p["proc"] = None

    i = 0
    while i < len(memoria) - 1:
        if memoria[i]["proc"] is None and memoria[i + 1]["proc"] is None:
            memoria[i]["tam"] += memoria[i + 1]["tam"]
            memoria.pop(i + 1)
        else:
            i += 1


def texto_cola(lista):
    """Formatea la visualización de una cola ordenada por tiempo restante (SRTF)."""
    if not lista:
        return "(vacía)"
    return "  ".join(f"{p['id']}(TR={p['restante']})" for p in sorted(lista, key=lambda x: x["restante"]))


def mostrar_estado(t, eventos, procs, memoria, en_cpu):
    """Muestra la fotografía completa del sistema en el instante t."""
    limpiar_pantalla()
    print("=" * 62)
    print(f" INSTANTE t = {t}")
    print("=" * 62)

    print("\nEventos:")
    for e in eventos:
        print(f"  - {e}")

    print("\nEstado del procesador:")
    if not en_cpu:
        print("  Ocioso (ningún proceso en ejecución)")
    else:
        print(f"  Ejecutando {en_cpu['id']} (restante {en_cpu['restante']} de {en_cpu['irrup']})")

    print("\nTabla de particiones de memoria:")
    print(f"  {'ID':<4}{'Comienzo':<10}{'Tamaño':<9}{'Proceso':<10}{'Frag. interna'}")
    for i, p in enumerate(memoria):
        nombre = p["proc"] or "(libre)"
        frag = "-" if not p["proc"] else 0
        print(f"  {i:<4}{p['inicio']:<10}{p['tam']:<9}{nombre:<10}{frag}")

    print("\nColas:")
    print(f"  Listos             : {texto_cola([p for p in procs if p['estado'] == 'Listo'])}")
    print(f"  Listos/Suspendidos : {texto_cola([p for p in procs if p['estado'] == 'Listo/Suspendido'])}")

    esperando = [p["id"] for p in procs if p["estado"] == "Nuevo" and p["llegada"] <= t]
    if esperando:
        print(f"  Nuevos sin admitir : {', '.join(esperando)}")

    print("\nProcesos:")
    print(f"  {'ID':<6}{'Estado':<19}{'Tamaño':<8}{'Restante'}")
    for p in procs:
        print(f"  {p['id']:<6}{p['estado']:<19}{p['tam']:<8}{p['restante']}")
    print("=" * 62)


def simular(procs):
    """Motor principal de simulación discreta tiempo a tiempo."""
    if not procs:
        input("\n[ERROR] No hay procesos para simular. Enter para volver...")
        return

    memoria = crear_memoria()
    en_cpu = None
    terminados = 0
    t = 0

    input(f"\n[INFO] Simulación lista con {len(procs)} procesos. Presiona Enter para comenzar...")

    while terminados < len(procs):
        eventos = []
        hay_evento = False

        # 1) Finalización del proceso actual en CPU
        if en_cpu and en_cpu["restante"] == 0:
            en_cpu.update({"estado": "Terminado", "fin": t})
            liberar(memoria, en_cpu["id"])
            eventos.append(f"{en_cpu['id']} terminó y liberó su partición.")
            en_cpu = None
            terminados += 1
            hay_evento = True

        # 2) Planificador de Mediano Plazo: Swapping-in (Listo/Suspendido -> Listo)
        for p in sorted([p for p in procs if p["estado"] == "Listo/Suspendido"], key=lambda x: x["restante"]):
            if asignar_best_fit(memoria, p):
                p["estado"] = "Listo"
                eventos.append(f"{p['id']}: Listo/Suspendido -> Listo (se le asignó memoria)")
                hay_evento = True

        # 3) Planificador de Largo Plazo: Admisión al sistema (Nuevo -> Listo o Listo/Suspendido)
        activos = sum(1 for p in procs if p["estado"] in ("Ejecutando", "Listo", "Listo/Suspendido"))
        for p in procs:
            if p["estado"] == "Nuevo" and p["llegada"] <= t:
                if p["llegada"] == t:
                    eventos.append(f"Arribo de {p['id']} (tamaño {p['tam']}K, irrupción {p['irrup']})")
                    hay_evento = True
                if activos < MAX_MULTI:
                    if asignar_best_fit(memoria, p):
                        p["estado"] = "Listo"
                        activos += 1
                        eventos.append(f"{p['id']}: Nuevo -> Listo (Best-Fit)")
                    else:
                        p["estado"] = "Listo/Suspendido"
                        activos += 1
                        eventos.append(f"{p['id']}: Nuevo -> Listo/Suspendido (sin memoria libre)")
                    hay_evento = True
                elif p["llegada"] == t:
                    eventos.append(f"{p['id']} queda en Nuevo (límite de multiprogramación: {MAX_MULTI})")
                    hay_evento = True

        # 4) Planificador de Corto Plazo: SRTF (Shortest Remaining Time First - Expropiativo)
        listos = [p for p in procs if p["estado"] == "Listo"]
        candidato = min(listos, key=lambda x: x["restante"], default=None) if listos else None

        if candidato:
            if not en_cpu:
                candidato["estado"] = "Ejecutando"
                en_cpu = candidato
                eventos.append(f"{candidato['id']} ingresa a la CPU")
                hay_evento = True
            elif candidato["restante"] < en_cpu["restante"]:
                eventos.append(
                    f"EXPROPIACIÓN: {en_cpu['id']} (restante {en_cpu['restante']}) "
                    f"cede la CPU a {candidato['id']} (restante {candidato['restante']})"
                )
                en_cpu["estado"] = "Listo"
                candidato["estado"] = "Ejecutando"
                en_cpu = candidato
                hay_evento = True

        # 5) Mostrar estado solo en instantes con cambios relevantes
        if hay_evento:
            mostrar_estado(t, eventos, procs, memoria, en_cpu)
            input("\nEnter para continuar...")

        # 6) Avance del reloj del sistema
        if en_cpu:
            en_cpu["restante"] -= 1
        t += 1

    # Informe estadístico final
    limpiar_pantalla()
    print("=" * 62)
    print(" INFORME ESTADÍSTICO")
    print("=" * 62)
    print(f"  {'ID':<6}{'Arribo':<8}{'Irrup.':<8}{'Fin':<6}{'Retorno':<9}{'Espera'}")

    sr, se = 0, 0
    for p in procs:
        retorno = p["fin"] - p["llegada"]
        espera = retorno - p["irrup"]
        sr += retorno
        se += espera
        print(f"  {p['id']:<6}{p['llegada']:<8}{p['irrup']:<8}{p['fin']:<6}{retorno:<9}{espera}")

    n = len(procs)
    print(f"\n  Tiempo total de simulación : {t}")
    print(f"  Tiempo de retorno promedio : {sr / n:.2f}")
    print(f"  Tiempo de espera promedio  : {se / n:.2f}")
    print(f"  Rendimiento del sistema    : {n / t:.4f} trabajos terminados por unidad de tiempo")
    print("=" * 62)
    input("\nEnter para volver al menú...")


def main():
    """Menú principal de la aplicación."""
    while True:
        limpiar_pantalla()
        print("=" * 56)
        print("   SIMULADOR DE PLANIFICACIÓN Y MEMORIA (MVT)")
        print("=" * 56)
        print(f" Memoria: {MEM_SO}K SO + {MEM_USUARIO}K usuario | Best-Fit | SRTF")
        print("-" * 56)
        print(" 1. Cargar procesos desde un archivo CSV")
        print(" 2. Cargar procesos manualmente")
        print(" 3. Salir")
        print("=" * 56)

        opcion = input("\nElige una opción (1-3): ").strip()
        if opcion == "1":
            nombre = input("Nombre del archivo (ej: lote1.csv): ").strip()
            simular(leer_archivo(nombre))
        elif opcion == "2":
            simular(cargar_manual())
        elif opcion == "3":
            break
        else:
            input("\n[ERROR] Opción inválida. Enter para continuar...")

    print("\n¡Gracias por usar el simulador!")


if __name__ == "__main__":
    main()