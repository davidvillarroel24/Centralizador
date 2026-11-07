-- Limpieza de materias duplicadas por el cambio de sigla "COM-" en Moodle (carrera_id=8).
-- VERSION 3: eliminacion logica (Materia.activo = false) en vez de DELETE, para evitar
-- cualquier riesgo justo antes de la demo. Requiere haber desplegado y corrido
-- "python manage.py migrate" primero (agrega la columna data_materia.activo).
--
-- 3 grupos:
--   (A) 2 pares donde la vieja SI tiene datos reales (unidades/accesos) y la COM- todavia
--       esta vacia: hay que MOVER esos datos a la COM- antes de inhabilitar la vieja.
--   (B) 1 caso (IEN-103) donde la COM- YA tiene los datos reales: la vieja se inhabilita
--       directo.
--   (C) 47 pares donde ambos lados estan vacios: se inhabilita la vieja directo.

-- =========================================================================
-- PASO 0 - Confirmar que la columna ya existe (si esto falla, todavia falta deployar/migrar).
-- =========================================================================
SELECT activo FROM data_materia LIMIT 1;

-- =========================================================================
-- PASO 1 - Revisar ANTES de tocar nada: confirmar que la situacion es la que yo vi.
-- =========================================================================
SELECT m.id, m.sigla, m.moodle_nombre, m.grupo, m.turno, m.gestion, m.activo,
       (SELECT count(*) FROM data_unidad u WHERE u.materia_id = m.id) AS unidades,
       (SELECT count(*) FROM data_accesocurso a WHERE a.materia_id = m.id) AS accesos
FROM data_materia m
WHERE m.id IN (315, 836, 374, 868, 334, 855)
ORDER BY m.id;
-- Esperado (igual que antes, mas la columna activo que ahora deberia dar TRUE en las 6):
--   315 CAM-102     -> unidades=8,  accesos=40
--   836 COM-CAM-102 -> unidades=0,  accesos=0
--   374 MIH-207     -> unidades=8,  accesos=41
--   868 COM-MIH-207 -> unidades=0,  accesos=0
--   334 IEN-103     -> unidades=0,  accesos=0
--   855 COM-IEN-103 -> unidades=8
-- Si algun numero no coincide, PARA Y AVISAME antes de seguir.

-- =========================================================================
-- PASO 2 (grupo A) - Mover los 2 pares con datos reales en la vieja hacia la COM-.
-- =========================================================================
BEGIN;

UPDATE data_unidad SET materia_id = 836 WHERE materia_id = 315;
UPDATE data_accesocurso SET materia_id = 836 WHERE materia_id = 315;

UPDATE data_unidad SET materia_id = 868 WHERE materia_id = 374;
UPDATE data_accesocurso SET materia_id = 868 WHERE materia_id = 374;

-- Verificacion antes de confirmar (tiene que dar 0, 0, 8, 8):
SELECT 315 AS materia, (SELECT count(*) FROM data_unidad WHERE materia_id=315) AS unidades
UNION ALL SELECT 374, (SELECT count(*) FROM data_unidad WHERE materia_id=374)
UNION ALL SELECT 836, (SELECT count(*) FROM data_unidad WHERE materia_id=836)
UNION ALL SELECT 868, (SELECT count(*) FROM data_unidad WHERE materia_id=868);

-- Si los 4 numeros de arriba son 0, 0, 8, 8 -> confirmar:
COMMIT;
-- Si algo salio mal -> en vez de COMMIT, correr: ROLLBACK;

-- =========================================================================
-- PASO 3 - Inhabilitar las 51 materias viejas (eliminacion logica, NO se borran).
-- Esto es lo unico distinto de la version anterior del script: UPDATE en vez de DELETE.
-- =========================================================================
UPDATE data_materia
SET activo = false
WHERE id IN (
    315, 374,  -- grupo A, ya vaciadas en el paso 2
    334,       -- grupo B (IEN-103, la COM- ya tenia los datos)
    305, 306, 307, 308, 309, 310, 311, 312, 313, 314, 316, 317, 318, 319, 320,
    321, 322, 323, 324, 325, 326, 327, 328, 329, 330, 331, 332, 333, 335, 336,
    337, 338, 339, 340, 368, 369, 370, 371, 372, 373, 375, 392, 393, 394, 395,
    396, 397, 398  -- grupo C, vacias de ambos lados
);
-- Debe decir "UPDATE 51". Nada se borra - si hace falta revertir una puntual, es
-- "UPDATE data_materia SET activo = true WHERE id = <el que sea>;", o desde el boton
-- en Materias (como Administrador) una vez deployado esto.
