# หน้าที่: เลือกภาพและโทนสีของระบบ
"""ภาพและโทนเดียวกันทั่วเว็บ โดยใช้ Streamlit และ Plotly จาก Python."""
from pathlib import Path
from image_generator import ASSETS_DIR
from common import image_path

RED='#C82543'
BURGUNDY='#471525'
SOFT_RED='#F2A3B3'
CHART_COLORS=[RED,'#487BE4','#865ED1','#27A184','#E6AC42']
RED_ASSETS=ASSETS_DIR/'red'

def hero_image():
    path=RED_ASSETS/'hero.webp'
    return path if path.exists() else ASSETS_DIR/'banner.png'

def equipment_image(row):
    original=Path(row.get('image') or '')
    if original.parent.as_posix()=='assets/equipment':
        photo=RED_ASSETS/f'{original.stem}.webp'
        if photo.exists():
            return photo
    return image_path(row.get('image'))

def style_chart(figure,height=260):
    figure.update_layout(height=height,margin=dict(l=5,r=5,t=15,b=5),
                         font=dict(family='SmartBorrow Thai, Noto Sans Thai, sans-serif',size=14),
                         paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)')
    figure.update_xaxes(showgrid=False)
    figure.update_yaxes(gridcolor='#EEE6E8',zeroline=False)
    return figure
