import pandas as pd

from services.utils.timing import medir_tiempo
from services.data_utils import cargarjson

@medir_tiempo
def generar_excel(estudiantes, archivo="notas.xlsx"):

    config_final = cargarjson.cargar_asignaciones()
    filas = []

    for est in estudiantes:
        fila = {"nombre": est["nombre"]}

        parciales_totales = []

        for i, parcial in enumerate(config_final["evaluaciones"], start=1):

            total_parcial = 0

            for cat_nombre, cat_data in parcial["categorias"].items():

                peso = cat_data["peso"]
                ids_tareas = cat_data["tareas"]

                notas_categoria = []

                for t in est["tareas"]:
                    if t["id"] in ids_tareas and t["nota"] is not None and t["max"]:

                        normalizada = (t["nota"] / t["max"]) * peso
                        notas_categoria.append(normalizada)

                # promedio si hay varias tareas
                if notas_categoria:
                    valor = sum(notas_categoria) / len(notas_categoria)
                else:
                    valor = 0

                col = f"P{i}_{cat_nombre}"
                fila[col] = round(valor, 2)

                total_parcial += valor

            fila[f"P{i}_total"] = round(total_parcial, 2)
            parciales_totales.append(total_parcial)

        # promedio final
        if parciales_totales:
            fila["final"] = round(sum(parciales_totales) / len(parciales_totales), 2)
        else:
            fila["final"] = 0

        filas.append(fila)

    # Crear DataFrame
    df = pd.DataFrame(filas)

    # Exportar a Excel
    df.to_excel(archivo, index=False)

    print(f"✅ Excel generado: {archivo}")
