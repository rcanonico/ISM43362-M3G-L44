###################################################################
# Driver for the WiFi module of the B-L475E-IOT01A ST board
# (C) 2025 - Roberto Canonico
# v1.0
###################################################################

from machine import Pin, SPI
from utime import sleep_ms, sleep_us
import sys

debug = False

SECURITY_MODES = {"Open": 0, "WEP": 1, "WPA": 2, "WPA2-AES": 3, "WPA2-Mixed": 4}

miso_pin = Pin('PC11', Pin.IN)
mosi_pin = Pin('PC12', Pin.OUT_PP)
csn_pin  = Pin('PE0',  Pin.OUT_PP)
drdy_pin = Pin('PE1',  Pin.IN)
rst_pin  = Pin('PE8',  Pin.OUT_PP)
wkup_pin = Pin('PB13', Pin.OUT_PP)

# This line MUST come after pin initialization
spi = SPI(3, baudrate=115200, polarity=0, phase=0, bits=8, firstbit=SPI.MSB)

# Default values for WiFi configuration parameters
SSID = "Test"
WIFI_PW = "Pass"
SECURITY= SECURITY_MODES.get("WPA2-AES")
DHCP_ENABLED = True 
SERVER = "ifconfig.io"

def ISM43362_ReadConfigFile(config_file='wifi.cfg'):
    global SSID, WIFI_PW, SECURITY, DHCP_ENABLED, SERVER
    try:
        with open(config_file, 'r') as file:
            wifi_cfg = file.read().splitlines()
            if debug:
                print("[wifi.cfg] =", wifi_cfg)
            for l in wifi_cfg:
                if l.startswith("SSID"):
                    SSID = l.split("=")[1]
                if l.startswith("WIFI_PW"):
                    WIFI_PW = l.split("=")[1]
                if l.startswith("SECURITY"):
                    s = l.split("=")[1]
                    if s in SECURITY_MODES:
                        SECURITY = SECURITY_MODES.get(s)
                    else:
                        SECURITY= SECURITY_MODES.get("WPA2-AES")
                if l.startswith("DHCP"):
                    if (l.split("=")[1] == "0"):
                        DHCP_ENABLED = False
                    else:
                        DHCP_ENABLED = True
                if l.startswith("SERVER"):
                    SERVER = l.split("=")[1]
    except OSError as e:
        print("[ISM43362] Unable to read configuration file")


def HTTP_ExtractHeaderValue(message, header_field, value_type):
    field_start = message.find(header_field)
    if (field_start != -1):
        next_crlf_pos = message.find("\r\n", field_start)
        header_value = message[field_start+len(header_field):next_crlf_pos].strip()
    else:
        header_value = ""
    if (value_type == int):
        return int(header_value)
    else:
        return header_value
        

def ISM43362_Data_Ready():
    return (drdy_pin.value() > 0)

def ISM43362_Reset():
    rst_pin(0)
    sleep_ms(10)
    rst_pin(1)
    sleep_ms(500)
    
def ISM43362_ChipSelect():
    csn_pin(0)
    sleep_us(1000)  

def ISM43362_ChipDeselect():
    csn_pin(1)
    sleep_us(1000)  

def ISM43362_Init():
    #wkup_pin(0)
    ISM43362_Reset()
    ISM43362_ChipSelect()
    data = b''   
    while ISM43362_Data_Ready():
        byte_read = spi.read(2, 0x0A)
        if byte_read != b'\x15\x15':
            data += bytes([byte_read[1],byte_read[0]])

    if (data != b'\r\n> '):
        raise RuntimeError("ISM43362 did not reply as expected after reset")
    

def ISM43362_SendCmd(cmd):
    # returns a string with received reply
    if debug:
        print("[ISM43362] sending command:", cmd)
        
    if (len(cmd) % 2 == 0):
        cmd += '\r\n'
    else:
        cmd += '\r'
        
    cmd_bytes = str.encode(cmd)
    
    ISM43362_ChipDeselect()
    ISM43362_ChipSelect()

    data = b''
    bytes_in = bytearray(2)
    bytes_out = bytearray(2)
    for i in range((len(cmd)+1) // 2):
        bytes_out = bytes([cmd_bytes[i*2+1], cmd_bytes[i*2]])
        # print(bytes_out)
        spi.write_readinto(bytes_out, bytes_in)
        data += bytes_in

    ISM43362_ChipDeselect()
    ISM43362_ChipSelect()
    while not ISM43362_Data_Ready():
        pass

    data = b''
    no_byte_read = 0
    while ISM43362_Data_Ready():
        byte_read = spi.read(2, 0x0A)
        if byte_read != b'\x15\x15':
            data += bytes([byte_read[1],byte_read[0]])

    ISM43362_ChipDeselect()
    # wait for data to be ready
    while not ISM43362_Data_Ready():
        pass

    # print("Data Received is", data)
    # Trim \x15 bytes at the end if any
    while (len(data) > 0) and (data[-1] == 0x15):
        data = data[:len(data)-1]
    # Trim leading \r\n
    if (len(data) >= 2) and (data[:2] == b'\r\n'):
        data = data[2:]
    # Trim ending prompt
    if (len(data) >= 8) and (data[len(data)-8:] == b'\r\nOK\r\n> '):
        data = data[:len(data)-8]
    if data == None:
        return "ERROR"
    else:
        return data
 
def ISM43362_GetFirmwareVersion():
    return ISM43362_SendCmd('I?').decode("utf-8")

def ISM43362_GetMAC():
    return ISM43362_SendCmd('Z5').decode("utf-8")

def ISM43362_SetAP_SSID(ssid):
    ISM43362_SendCmd('C1='+ssid).decode("utf-8")
    return

def ISM43362_SetAP_Password(pw):
    ISM43362_SendCmd('C2='+pw).decode("utf-8")
    return

# mode: 0=Open, 1=WEP, 2=WPA, 3= WPA2-AES, 4= WPA2-Mixed
def ISM43362_SetAP_SecurityType(mode):
    if mode not in range(0,5):
        mode = 0
    ISM43362_SendCmd('C3='+str(mode)).decode("utf-8")
    return

def ISM43362_EnableDHCP(dhcp):
    if (dhcp == False) or (dhcp == 0):
        dhcp = 0
    else:
        dhcp = 1
    ISM43362_SendCmd('C4='+str(dhcp)).decode("utf-8")
    return

def ISM43362_JoinAP():
    reply = ISM43362_SendCmd('C0').decode("utf-8")
    last_join_pos = reply.rfind("[JOIN   ]") 
    status = reply[last_join_pos+10:reply.find("\r\n", last_join_pos)]
    if status == "Failed":
        print("[ISM43362] ERROR: unable to connect to AP (SSID=%s)" % SSID)

def ISM43362_GetStatus():
    return ISM43362_SendCmd('C?').decode("utf-8")

def ISM43362_IsConnected():
    reply = ISM43362_SendCmd('C?').decode("utf-8")
    reply_splitted = reply.split(',')
    return (reply_splitted[-1] == '1')

def ISM43362_GetIP():
    reply = ISM43362_SendCmd('C?').decode("utf-8")
    reply_splitted = reply.split(',')
    if ((reply_splitted[-1] == '1')):
        return (reply_splitted[5])
    else:
        return '0.0.0.0'

def ISM43362_GetNetmask():
    reply = ISM43362_SendCmd('C?').decode("utf-8")
    reply_splitted = reply.split(',')
    if ((reply_splitted[-1] == '1')):
        return (reply_splitted[6])
    else:
        return '0.0.0.0'

def ISM43362_GetDefaultGateway():
    reply = ISM43362_SendCmd('C?').decode("utf-8")
    reply_splitted = reply.split(',')
    if ((reply_splitted[-1] == '1')):
        return (reply_splitted[7])
    else:
        return '0.0.0.0'

def ISM43362_DNS1():
    reply = ISM43362_SendCmd('C?').decode("utf-8")
    reply_splitted = reply.split(',')
    if ((reply_splitted[-1] == '1')):
        return (reply_splitted[8])
    else:
        return '0.0.0.0'

def ISM43362_DNS2():
    reply = ISM43362_SendCmd('C?').decode("utf-8")
    reply_splitted = reply.split(',')
    if ((reply_splitted[-1] == '1')):
        return (reply_splitted[9])
    else:
        return '0.0.0.0'

def ISM43362_DNS_Lookup(hostname):
    return ISM43362_SendCmd('D0='+hostname).decode("utf-8")
   
def ISM43362_Send_HTTP_Request(server=SERVER, port=80, method='GET', url='/', body=None, timeout=5000):
    if not ISM43362_IsConnected():
        return ""
    request_headers = 'Host: %s\r\nConnection: close\r\n\r\n' % server
    http_request = method+' '+url+' '+'HTTP/1.0\r\n'+request_headers
    l = str(len(http_request))
    server_ip = ISM43362_DNS_Lookup(server)
    ISM43362_SendCmd('P1=0').decode("utf-8")
    ISM43362_SendCmd('P3='+server_ip).decode("utf-8")
    ISM43362_SendCmd('P4='+str(port)).decode("utf-8")
    ISM43362_SendCmd('P6=1').decode("utf-8")
    ISM43362_SendCmd('S3='+l+'\r'+http_request).decode("utf-8")
    ISM43362_SendCmd('R1=1460').decode("utf-8")
    ISM43362_SendCmd('R2='+str(timeout)).decode("utf-8")
    count = 0
    header_fully_received = False
    response = ""
    while not header_fully_received:
        count += 1
        data_read = ISM43362_SendCmd('R0').decode("utf-8")
        if data_read.startswith("-1"):
            continue
        response += data_read
        if debug:
            print("R0 - Reply (%d):" % count, data_read)
        header_end_pos = response.find('\r\n\r\n')
        header_fully_received = (header_end_pos != -1)

    content_length = HTTP_ExtractHeaderValue(response, "Content-Length:", int)
    body_byte_counter = len(response) - (header_end_pos + 4)
    if (body_byte_counter >= content_length):
        body_fully_received = True
    else:
        body_fully_received = False
        while not body_fully_received:
            count += 1
            data_read = ISM43362_SendCmd('R0').decode("utf-8")
            if data_read.startswith("-1"):
                continue
            response += data_read
            if debug:
                print("R0 - Reply (%d):" % count, data_read)
            body_byte_counter = len(response) - (header_end_pos + 4)
            body_fully_received = (body_byte_counter >= content_length)

    ISM43362_SendCmd('P6=0').decode("utf-8")
    if (body_fully_received):
        body = response[header_end_pos+4:]
    else:
        body = ""
    return body


def ISM43362_GetPublicIP():
    response = ISM43362_Send_HTTP_Request(server='ifconfig.io', url='/ip')
    return response


def ISM43362_TestModule():
    firmware_version = ISM43362_GetFirmwareVersion()
    print("[ISM43362] firmware:", firmware_version)
    
    MAC_address = ISM43362_GetMAC()
    print("[ISM43362] WiFi MAC address:", MAC_address)

    ISM43362_SetAP_SSID(SSID)
    ISM43362_SetAP_Password(WIFI_PW)
    ISM43362_SetAP_SecurityType(SECURITY)
    ISM43362_EnableDHCP(DHCP_ENABLED)
    connection_ok = ISM43362_JoinAP()

    if debug:
        status = ISM43362_GetStatus()
        print("[ISM43362] status:", status)

    if not ISM43362_IsConnected():
        print("[ISM43362] status: UNCONNECTED")
        sys.exit(1)
        
    print("[ISM43362] status: CONNECTED")
    ip = ISM43362_GetIP()
    nm = ISM43362_GetNetmask()
    dg = ISM43362_GetDefaultGateway()
    dns1 = ISM43362_DNS1()
    dns2 = ISM43362_DNS2()
    server_ip = ISM43362_DNS_Lookup(SERVER)
    public_ip = ISM43362_GetPublicIP()
    print("[ISM43362] IP ADDR:", ip)
    print("[ISM43362] NETMASK:", nm)
    print("[ISM43362] GW ADDR:", dg)
    print("[ISM43362]    DNS1:", dns1)
    print("[ISM43362]    DNS2:", dns2)
    print("[ISM43362] SERVER IP:", server_ip)
    print("[ISM43362] PUBLIC IP:", public_ip)

if __name__ == "__main__":
    if debug:
        print("[ISM43362] SPI settings:",spi)
    ISM43362_ReadConfigFile()
    ISM43362_Init()
    ISM43362_TestModule()
