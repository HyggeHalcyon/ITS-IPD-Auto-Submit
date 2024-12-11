from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
from bs4 import BeautifulSoup
from typing import List, Tuple
from settings import *
from pwn import log
import requests
import urllib3
import base64
import json
import re

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
proxy = {'http': 'http://127.0.0.1:8080', 'https': 'http://127.0.0.1:8080'} # burp debug

def encrypt(username, password, pubkey) -> bytes:
    public_key = RSA.importKey(pubkey)
    cipher = PKCS1_v1_5.new(public_key)

    plaintext = {
        "u": username,
        "p": password,
        "dm": '',
        "ps": ''
    }

    plaintext_str = json.dumps(plaintext)
    encrypted_data = cipher.encrypt(plaintext_str.encode('utf-8'))
    encrypted_base64 = base64.b64encode(encrypted_data).decode('utf-8')

    return encrypted_base64

def login():
    res = client.get(
        'https://my.its.ac.id/signin' + \
        '?response_type=code' + \
        '&redirect_uri=https%3A%2F%2Fportal.its.ac.id%2Fapi%2Fauth' + \
        f'&client_id={CLIENT_ID}' + \
        f'&nonce={NONCE}' + \
        f'&state={STATE}' + \
        '&scope=group+resource+role+openid'
        )

    if res.status_code != 200:
        log.failure('failed to get login page')
        exit(1)

    soup = BeautifulSoup(res.text, 'html.parser')
    try:
        pubkey = soup.find('input', {'id': 'pubkey'})['value']
        pubkey = pubkey.replace("\t", "")
        log.info(pubkey)
    except Exception as e:
        log.failure('failed to get pubkey')
        exit(1)

    content = encrypt(NRP, PASSWORD, pubkey)
    try:
        res = client.post('https://my.its.ac.id/signin', data={
            'client_id': CLIENT_ID,
            'response_type': 'code',
            'scope': 'group resource role openid',
            'state': STATE,
            'prompt': '',
            'redirect_uri': 'https://portal.its.ac.id/api/auth',
            'nonce': NONCE,
            'content': content,
            'password_state': True,
            'device_method': ''
        }, allow_redirects=True)
    except Exception as e:
        log.failure("failed to login")
        print(e)
        exit(1)

    if res.status_code != 200:
        log.failure('failed to login')
        exit(1)

    for c in client.cookies:
        log.info("%s | %s | %s", c.name, c.value, c.domain)

def get_courses() -> Tuple[List[str], List[str]]:
    client.get("https://akademik.its.ac.id/home.php", allow_redirects=True)
    res = client.get("https://akademik.its.ac.id/ipd_kuesionermk.php", allow_redirects=True)

    soup = BeautifulSoup(res.text, 'html.parser')
    value_pattern = r'<option\s+[^>]*value=["\']([^"\']+)["\']'
    str_pattern = r'<option[^>]*value="[^"]+"[^>]*>(.*?)</option>'

    try:
        select = soup.find('select', {'name': 'mk_kuesioner', 'id': 'mk_kuesioner'})
        courses_code = re.findall(value_pattern, str(select ))
        courses_detail = re.findall(str_pattern, str(select))
    except Exception as e:
        log.failure(f'Failed to parse the course list: {e}')
        exit(1)
    
    for i in range(len(courses_code)):
        log.success(f'{courses_code[i]}: {courses_detail[i]}')
    return courses_code, courses_detail

def change_to_course_ipd(code) -> bool:
    res = client.post("https://akademik.its.ac.id/ipd_kuesionermk.php", data={
        "semesterTerm": SEMESTER_TERM,
        "thnAjaran": TAHUN_AJARAN,
        "act": "mkchange",
        "key": "",
        "scroll": "",
        "page": "1",
        "sort": "1",
        "filter": "",
        "mk_kuesioner": code
    })

    if res.status_code != 200:
        log.failure('failed to change course: %s', code)
        exit(1)
    
    if 'Anda sudah mengisi kuesioner untuk matakuliah ini' in res.text:
        return False
    return True

def submit_course_ipd():
    res = client.post("https://akademik.its.ac.id/ipd_kuesionermk.php", data={
        "act": "inputKuesioner",
        "MK1": DEFAULT_PENILAIAN,
        "MK2": DEFAULT_PENILAIAN,
        "MK3": DEFAULT_PENILAIAN,
        "MK4": DEFAULT_PENILAIAN,
        "MK5": DEFAULT_PENILAIAN,
        "MK6": DEFAULT_PENILAIAN,
        "MK7": DEFAULT_PENILAIAN,
        "MK8": DEFAULT_PENILAIAN,
        "MK9": DEFAULT_PENILAIAN,
        "MK10": DEFAULT_PENILAIAN,
        "txtKomentar": "",
        "chkPermanent": "1",
        "button": "SIMPAN"
    })

def get_lecturer_list(code) -> List[str]:
    res = client.post("https://akademik.its.ac.id/ipd_kuesionermk.php", data={
        "semesterTerm": SEMESTER_TERM,
        "thnAjaran": TAHUN_AJARAN,
        "act": "mkchange",
        "key": "",
        "scroll": "",
        "page": "1",
        "sort": "1",
        "filter": "",
        "mk_kuesioner": code
    })

    soup = BeautifulSoup(res.text, 'html.parser')
    href_pattern = r'href="([^"]+)"'

    try:
        form = soup.find('form', {'name': 'form2', 'id': 'form2'})
        lecturer_path = re.findall(href_pattern, str(form))

        table = form.find('table', {'class': 'FilterBox'})
        entries = table.find_all('tr')
        for entry in entries:
            if 'Isi Kuesioner' in entry.text:
                continue
            lecturer_name = entry.find('td').text.split("-")[1].strip()
            log.success("IPD dosen %s sudah terisi", lecturer_name)

        return lecturer_path
    except Exception as e:
        log.failure(f'Failed to parse the lecturer list: {e}')
        exit(1)

def change_to_lecturer_ipd(path) -> bool:
    res = client.get(f'https://akademik.its.ac.id/{path}', allow_redirects=True)

    soup = BeautifulSoup(res.text, 'html.parser')
    h3_pattern = pattern = r'<h3>(.*?)</h3>'

    try:
        form = soup.find('form', {'name': 'form2', 'id': 'form2'})
        lecturer_name = re.findall(h3_pattern, str(form))
    except Exception as e:
        log.failure(f'Failed to parse the lecturer page: {e}')
        exit(1)

    if 'Anda sudah mengisi kuesioner untuk dosen di matakuliah ini' in res.text:
        log.success("IPD dosen %s sudah terisi", lecturer_name[1])
        return False
    log.info("mengisi IPD dosen %s", lecturer_name[1])
    return True

def submit_lecturer_ipd():
    res = client.post("https://akademik.its.ac.id/ipd_kuesionerdosen.php", data={
        "act": "inputKuesioner",
        "DO1": DEFAULT_PENILAIAN,
        "DO2": DEFAULT_PENILAIAN,
        "DO3": DEFAULT_PENILAIAN,
        "DO4": DEFAULT_PENILAIAN,
        "DO5": DEFAULT_PENILAIAN,
        "DO6": DEFAULT_PENILAIAN,
        "DO7": DEFAULT_PENILAIAN,
        "DO8": DEFAULT_PENILAIAN,
        "DO9": DEFAULT_PENILAIAN,
        "DO10": DEFAULT_PENILAIAN,
        "txtKomentar": "",
        "chkPermanent": "1",
        "button": "SIMPAN"
    })

def main():
    login()
    codes, details = get_courses()

    # ipd mata kuliah
    for i, code in enumerate(codes):
        if(change_to_course_ipd(code)):
            log.info("mengisi IPD mata kuliah %s", details[i].split("-")[1].strip())
            submit_course_ipd()
        else:
            log.success("IPD mata kuliah %s sudah terisi", details[i].split("-")[1].strip())

    # ipd dosen
    for code in enumerate(codes):
        lecturers = get_lecturer_list(code)
        for lecturer in lecturers:
            if(change_to_lecturer_ipd(lecturer)):
                submit_lecturer_ipd()

if __name__ == '__main__':
    global client
    client = requests.Session()
    main()