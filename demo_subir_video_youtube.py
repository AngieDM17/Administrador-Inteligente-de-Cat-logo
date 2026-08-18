"""Demo para la revision de cupo de la YouTube Data API (Google, 13-ago-2026):
graba la pantalla mostrando este codigo y corriendolo -- es EXACTAMENTE el
mismo camino que usa el pipeline real (orquestador.py -> youtube_uploader.
subir_video()), no una version aparte hecha para la ocasion.

Como usar:
    python demo_subir_video_youtube.py
"""

from pathlib import Path

from youtube_uploader import subir_video

RUTA_VIDEO = Path(
    "investigaciones/TOP250414656_bicicleta-estatica-spinning-resistencia-"
    "magnetica-y-transmision-por-correa/TOP250414656_video_final.mp4"
)

TITULO = "BICICLETA ESTATICA SPINNING - RESISTENCIA MAGNETICA Y TRANSMISION POR CORREA (demo)"
DESCRIPCION = (
    "Bicicleta estatica de spinning, resistencia magnetica y transmision "
    "por correa.\n"
    "Ekipon.co - equipos para tu negocio, con envio a todo Colombia.\n\n"
    "Video de demostracion para la revision de cupo de la YouTube Data "
    "API -- el video final ya se habia subido antes con este mismo "
    "script; esta subida es solo para mostrarle a Google el script en "
    "ejecucion."
)

if __name__ == "__main__":
    print(f"Subiendo '{RUTA_VIDEO.name}' al canal de YouTube de Ekipon...")
    resultado = subir_video(RUTA_VIDEO, TITULO, DESCRIPCION)
    print("Listo. Video publicado en:", resultado["url"])
