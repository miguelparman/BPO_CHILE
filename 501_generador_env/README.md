# 501_generador_env

Empaqueta los archivos `.env` de todos los proyectos de BPO_CHILE en un `.7z`
cifrado (AES-256, con nombres cifrados) para copiarlos a otra maquina, y los
restaura alli en su carpeta de origen.

Los `.env` no se versionan en git; esta es la via soportada para moverlos.

## Requisitos

- Python 3.10+ (solo libreria estandar, sin dependencias).
- [7-Zip](https://www.7-zip.org) instalado (`7z.exe` en el PATH o en `Program Files`).

## Uso

En la maquina de origen:

```
python main.py exportar
```

Crea `env_backup.7z` dentro de este proyecto (`501_generador_env/`); su
`.gitignore` ignora `*.7z`, asi que git nunca lo ve. Muestra una clave aleatoria. Envie la clave por un canal distinto al del archivo.
Opcional: `--salida RUTA.7z`.

En la maquina de destino (con el repo ya clonado y el `.7z` copiado):

```
python main.py importar ruta\a\env_backup.7z
```

Pide la clave y deja cada `.env` en su proyecto. No sobrescribe `.env`
existentes. Despues:

1. Borre el `.7z` en ambas maquinas.
2. Revise rutas propias de la maquina (p. ej. `D:\...`).
3. Instale las dependencias de cada proyecto.

## Que incluye / excluye

Incluye todo `.env` bajo BPO_CHILE, excepto en `Basurero/`, `Migrar/`, `.venv/`,
`venv/`, `node_modules/` y `.git/` (editar `EXCLUIR` en `main.py`).

## Notas de seguridad

- La clave se pasa a `7z` por linea de comandos: durante unos segundos es visible
  en la lista de procesos de la maquina. Aceptable en equipos propios.
- Nunca suba el `.7z` a git, correo o carpetas compartidas abiertas.
