from datetime import datetime


def parsear_fecha(fecha_str):
    if not fecha_str:
        return None

    meses = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
        "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
        "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
    }

    try:
        partes = fecha_str.lower().split(",")
        fecha = partes[1].strip()  # "14 de abril de 2025"
        dia, _, mes, _, anio = fecha.split()
        mes_num = meses[mes]

        return datetime(int(anio), mes_num, int(dia))
    except:
        return None


def detectar_categoria(titulo):
    t = titulo.lower()

    if "mi-tek" in t or "mitek" in t:
        return "mitek"
    elif "e-tek" in t or "etek" in t:
        return "etek"
    elif "design" in t:
        return "designlab"
    elif "exam" in t or "examen" in t:
        return "examen"
    else:
        return "training"


def obtener_parcial(fecha, rangos):
    if not fecha:
        return None

    for r in rangos:
        if not r["inicio"] or not r["fin"]:
            continue

        inicio = datetime.fromisoformat(r["inicio"])
        fin = datetime.fromisoformat(r["fin"])

        if inicio <= fecha <= fin:
            return r["parcial"]

    return None


def auto_asignar_tareas(tareas, rangos_parciales):
    resultado = []

    for t in tareas:
        fecha = parsear_fecha(t["cierre"])
        categoria = detectar_categoria(t["titulo"])
        parcial = obtener_parcial(fecha, rangos_parciales)

        resultado.append({
            "id": t["id"],
            "titulo": t["titulo"],
            "categoria": categoria,
            "parcial": parcial
        })

    return resultado

def mostrar_resumen_tareas(asignaciones, ordenar=False):

    lista = asignaciones

    if ordenar:
        def clave_orden(t):
            parcial = t["parcial"] if t["parcial"] is not None else 99
            categoria = t["categoria"] or ""
            titulo = t["titulo"]
            return (parcial, categoria, titulo)

        lista = sorted(asignaciones, key=clave_orden)

    print("\n=== RESUMEN DE TAREAS ===\n")

    for i, t in enumerate(lista, start=1):

        parcial = t["parcial"] if t["parcial"] is not None else "❌"
        categoria = t["categoria"].upper() if t["categoria"] else "❌"

        print(f"{i}) [{t['id']}] {t['titulo']}")
        print(f"   → {categoria} | Parcial: {parcial}\n")

    return lista

def editar_tareas_interactivamente(asignaciones):
    
    categorias_validas = {
        "M": "mitek",
        "E": "etek",
        "T": "training",
        "D": "designlab",
        "X": "examen"
    }

    while True:
        try:
            opcion = input("\nIngrese el número de la tarea a editar (0 para continuar): ").strip()

            if not opcion:
                continue

            opcion = int(opcion)

            if opcion == 0:
                break

            if opcion < 1 or opcion > len(asignaciones):
                print("❌ Número inválido")
                continue

            tarea = asignaciones[opcion - 1]

            print(f"\nEditando: {tarea['titulo']} (ID: {tarea['id']})")
            print(f"Actual → Categoría: {tarea['categoria']} | Parcial: {tarea['parcial']}")

            # --- editar categoría ---
            nueva_cat = input("Nueva categoría (M/E/T/D/X o Enter para mantener): ").upper().strip()

            if nueva_cat:
                if nueva_cat in categorias_validas:
                    tarea["categoria"] = categorias_validas[nueva_cat]
                else:
                    print("❌ Categoría inválida (no se cambió)")

            # --- editar parcial ---
            nuevo_parcial = input("Nuevo parcial (1-4 o Enter para mantener): ").strip()

            if nuevo_parcial:
                if nuevo_parcial in ["1", "2", "3", "4"]:
                    tarea["parcial"] = int(nuevo_parcial)
                else:
                    print("❌ Parcial inválido (no se cambió)")

            print("✅ Tarea actualizada")

            # 🔥 volver a mostrar resumen actualizado
            mostrar_resumen_tareas(asignaciones, ordenar=False)

        except ValueError:
            print("❌ Entrada inválida, intenta nuevamente")

    return asignaciones

def generar_config_final(asignaciones, config_base):

    pesos = config_base["pesos_default"]
    rangos = config_base["rangos_parciales"]

    # Crear estructura base de parciales
    parciales_map = {}

    for r in rangos:
        p = r["parcial"]

        parciales_map[p] = {
            "nombre": f"Parcial {p}",
            "categorias": {
                cat: {
                    "peso": pesos.get(cat, 0),
                    "tareas": []
                }
                for cat in pesos.keys()
            }
        }

    # Llenar tareas
    errores = []

    for t in asignaciones:
        parcial = t["parcial"]
        categoria = t["categoria"]
        tarea_id = t["id"]

        if not parcial or not categoria:
            errores.append(t)
            continue

        if parcial not in parciales_map:
            errores.append(t)
            continue

        parciales_map[parcial]["categorias"][categoria]["tareas"].append(tarea_id)

    # Convertir a lista ordenada
    config_final = {
        "evaluaciones": list(parciales_map.values())
    }

    return config_final, errores
