import os
import numpy as np
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

st.set_page_config(layout="wide", page_title="시공사 점유율 & 정비사업 대시보드")
st.title("LH 데이터 분석 앱")

data_path = "./data"
서울시APT = pd.read_csv(f"{data_path}/서울시_공동주택_1차전처리.csv")
