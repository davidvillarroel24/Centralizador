def extraer_tareas_planas(tareas_json):
    tareas_planas = []

    for curso in tareas_json:
        curso_id = curso.get("id")
        asignatura = curso.get("asignatura")

        for unidad in curso.get("tareas", []):
            for item in unidad.get("contenido", []):

                # Solo nos interesan tareas calificables (assign)
                url = item.get("url", "")
                if "assign/view.php" not in url:
                    continue

                tarea = {
                    "id": item.get("id"),
                    "titulo": item.get("Titulo", "").strip(),
                    "cierre": item.get("cierre"),
                    "curso_id": curso_id,
                    "asignatura": asignatura,
                }

                tareas_planas.append(tarea)

    return tareas_planas

