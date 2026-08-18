#Encargado de manejar la sesión y autenticación.
import json
import requests
import re
from gatfh import config

from services.data_utils import exportarjson

class MoodleSession:
    def __init__(self):
        self.base_url = config.BASE_URL
        self.cookies = config.COOKIES
        self.session = requests.Session()
        self.session.cookies.update(self.cookies)

    def get(self,**kwargs):        
        # ------------------------------
        # Paso 1: obtener sesskey
        # ------------------------------
        self.session.cookies.update(self.cookies)
        URL=f"{self.base_url}"
        resp = self.session.get(URL)
        html_text = resp.text

        # Buscar sesskey dentro de M.cfg
        match = re.search(r'"sesskey":"([a-zA-Z0-9]+)"', html_text)
        if not match:
            raise Exception("No se pudo extraer el sesskey.")

        sesskey = match.group(1)
        config.SESSKEY = sesskey  # 🔥 guardado global
        self.guardar_sesskey(sesskey)

        if not sesskey:
            raise Exception("No se pudo extraer el sesskey. Revisa tu cookie de sesión.")
        print("Sesskey obtenido:", sesskey)
        return sesskey
    

    def guardar_sesskey(self,sesskey):
        with open(config.JSON_SESSKEY, "w") as f:
            json.dump({"SESSKEY": sesskey}, f)

    def cargar_sesskey(self):
        try:
            with open(config.JSON_SESSKEY, "r") as f:
                return json.load(f)["SESSKEY"]
        except:
            return None
                    
    def get_sesskey(self):
        sesskey = self.cargar_sesskey()

        #if sesskey:
        #    if self.sesskey_valido(sesskey):
        #        print("✔ Reutilizando sesskey")
        #        return sesskey
        #    else:
        #        print("⚠ Sesskey expirado")

        return self.get()
    
    def sesskey_valido(self, sesskey):
        try:

            url = f"{self.base_url}/lib/ajax/service.php?sesskey={sesskey}&info=core_webservice_get_site_info"

            resp = self.session.post(url, json=[{
                "index": 0,
                "methodname": "core_webservice_get_site_info",
                "args": {}
            }])

            result = resp.json()            
            exportarjson.save_sesskey(result)

            if isinstance(result, list) and result[0].get("error"):
                errorcode = result[0]["exception"].get("errorcode")
                return errorcode != "invalidsesskey"

            return True

        except:
            return False
    
    def get_courses(self, endpoint):
        
        cookies=config.COOKIES['MoodleSession']
        print("Cookies: ",cookies)
        sesskey = self.get_sesskey()
        print("sesskey: ",sesskey)
        COURSES_URL=f"{self.base_url}{endpoint}"
        print("COURSES_URL: ",COURSES_URL)

        ajax_url = f"{self.base_url}/lib/ajax/service.php?sesskey={sesskey}&info=core_course_get_enrolled_courses_by_timeline_classification"

        data_raw = '[{"index":0,"methodname":"core_course_get_enrolled_courses_by_timeline_classification","args":{"offset":0,"limit":0,"classification":"all","sort":"fullname","customfieldname":"","customfieldvalue":""}}]'

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:142.0) Gecko/20100101 Firefox/142.0",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "es-ES,es;q=0.8,en-US;q=0.5,en;q=0.3",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": self.base_url,
            "Connection": "keep-alive",
            "Referer": COURSES_URL,
            "Cookie": f"MoodleSession={cookies}",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "TE": "trailers"
        }

        resp2 = self.session.post(ajax_url, headers=headers, data=data_raw)
        data = resp2.json() 

        return data
        #return self.session.get(f"{self.base_url}{endpoint}", **kwargs)

    def post(self, endpoint, **kwargs):
        return self.session.post(f"{self.base_url}{endpoint}", **kwargs)

    #def get_category(self, endpoint,category_id=0):
    #    
    #    cookies=config.COOKIES['MoodleSession']
    #    print("Cookies: ",cookies)
    #    sesskey = self.get_sesskey()
    #    print("sesskey: ",sesskey)
    #    COURSES_URL=f"{self.base_url}{endpoint}"
    #    print("COURSES_URL: ",COURSES_URL)
#
    #    data = {
    #        "categoryid": category_id,
    #        "depth": 5,
    #        "showcourses": 1000,
    #        "type": 0
    #    }
#
    #    headers = {
    #        "User-Agent": "Mozilla/5.0",
    #        "X-Requested-With": "XMLHttpRequest",
    #        "Referer": f"{self.base_url}/course/index.php"
    #    }
#
    #    resp = self.session.post(COURSES_URL, data=data, headers=headers)
#
    #    return resp.text
    
    def get_category(self, endpoint, category_id=0, page=0):
        
        cookies=config.COOKIES['MoodleSession']
        #print("Cookies: ",cookies)
        sesskey = self.get_sesskey()
        #print("sesskey: ",sesskey)

        COURSES_URL = f"{self.base_url}{endpoint}"
        print(COURSES_URL)
        data = {
            "categoryid": category_id,
            "browse": "courses",
            "perpage": 20,
            "page": page
        }

        headers = {
            "User-Agent": "Mozilla/5.0",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{self.base_url}/course/index.php"
        }

        resp = self.session.post(
            COURSES_URL,
            data=data,
            headers=headers
        )

        return resp.text
