#! /env/Scripts/activate 

###!/usr/bin/env python

"""\
Demo: dial a number (simple example using polling to check call status)

Simple demo app that makes a voice call and plays sone DTMF tones (if supported by modem)
when the call is answered, and hangs up the call.
It polls the call status to see if the call has been answered

Note: you need to modify the NUMBER variable for this to work
"""

from __future__ import print_function

import serial, sys, re, time, logging

PORT = 'COM5'
BAUDRATE = 115200
NUMBER1 = '3383301889' # Number to dial - CHANGE THIS TO A REAL NUMBER
NUMBER2 = '00000' # Number to dial - CHANGE THIS TO A REAL NUMBER
PIN = None # SIM card PIN (if any)
fsm_status = "IDLE"
SMS_TEXT = 'A good teacher is like a candle, it consumes itself to light the way for others.'
RAT_NAME = ("GSM", "GSM Compact", "UTRAN", "Unknown", "Unknown", "Unknown", "Unknown" , "EUTRAN", "CDMA/HDR")

from gsmmodem.modem import GsmModem, SentSms
from gsmmodem.exceptions import CommandError, CmsError, CmeError, InvalidStateException, TimeoutException
from gsmmodem.util import lineMatching
from inputimeout import inputimeout, TimeoutOccurred

class LteModem(GsmModem):
    @property
    def networkRAT(self):
        """ :return: the RAT of Network Operator to which the modem is connected """
        #COPS_RAT_PARSER = re.compile('^\+CSQ:\s*(\d+),')
       
        copsMatchRat = lineMatching('^\+COPS: (\d),(\d),"(.+)",(\d)*$', self.write('AT+COPS?')) # response format: +COPS: mode,format,"operator_name",x
        if copsMatchRat:
            return copsMatchRat.group(4)
    
    @property
    def networkDataRegistered(self):
        """ :return: Network Data Registration """
        # Check ESP Network registration
        cxregMatch = lineMatching('^\+CEREG: (\d),(\d)', self.write('AT+CEREG?')) # response format: +COPS: mode,format,"operator_name",x
        if cxregMatch:
            if cxregMatch.group(2) == '1' or cxregMatch.group(2) == '5':
                return cxregMatch.group(2)
        # Check GPRS Network registration
        time.sleep(0.5)
        cxregMatch = lineMatching('^\+CGREG: (\d),(\d)', self.write('AT+CGREG?')) # response format: +COPS: mode,format,"operator_name",x
        if cxregMatch:
            return cxregMatch.group(2)
    
    @property
    def StartNDIS(self):
        #AT+CUSBPIDSWITCH=9001,1,1
        self.write('AT+CUSBPIDSWITCH=9001,1,1', parseError=False)
        time.sleep(0.5)
        #AT$QCRMCALL=1,1 --> $QCRMCALL: 1, V4
        qcrmcallMatch = lineMatching('^\$QCRMCALL: 1, V4', self.write('AT$QCRMCALL=1,1')) # response format: +COPS: mode,format,"operator_name",x
        if qcrmcallMatch:
            return 1
        else:
            return 0


def handleSms(sms):
    fsm_status = "BUSY"
    print(u'== SMS message received ==\nFrom: {0}\nTime: {1}\nMessage:\n{2}\n'.format(sms.number, sms.time, sms.text))
    print('Replying to SMS...')
    sms.reply(u'SMS received: "{0}{1}"'.format(sms.text[:20], '...' if len(sms.text) > 20 else ''))
    print('SMS sent.\n')
    fsm_status = "IDLE"

def callStatusCallback(call):
    global waitForCallback
    print('Call status update callback function called')
    if call.answered:
        print('Call has been answered; waiting a while...')
        # Wait for a bit
        for call_timeout in range(30):
            time.sleep(1.0)

        if call.active: # Call is still active
            print('Hanging up call...')
            call.hangup()
    else:
        # Call is no longer active (remote party ended it)
        print('Call has been ended by remote party')
    waitForCallback = False

def handleIncomingCall(call):
    if call.ringCount == 1:
        print('Incoming call from:', call.number)
    elif call.ringCount >= 5:
        call.answer()
        for call_timeout in range(20):
            time.sleep(1.0)
            if not call.active:
                break;

        if call.active: # Call is still active
            print('Hanging up call.')
            call.hangup()
    else:
        print(' Call from {0} is still ringing...'.format(call.number))
    fsm_status = "IDLE"


def main():
    print('Initializing modem...')
    logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.DEBUG)
    #modem = GsmModem(PORT, BAUDRATE, incomingCallCallbackFunc=handleIncomingCall, smsReceivedCallbackFunc=handleSms)

    modem = LteModem(PORT, BAUDRATE, incomingCallCallbackFunc=handleIncomingCall, smsReceivedCallbackFunc=handleSms)
    modem.smsTextMode = False
    print('Connecting modem...')
    
    for connect_timeout in range(6):
        try:
            modem.connect(PIN)
            break
        except (serial.SerialException, CmeError, TimeoutException) as s_err:
            print('Connection Erorr:  {0} (Error {1})'.format(s_err, s_err.__cause__))
            print('Retry to connect')
            time.sleep(5)
    else:
        exit()

    imsi_sim = modem.imsi
    #Set APN
    APN  = {'name': '', 'user':'','pwd':''}
    MCC_SIM = imsi_sim[0:3]
    MNC_SIM = imsi_sim[3:5]

    if (MCC_SIM == '222'):
        # OPERATORE ITALIANO
        if (MNC_SIM == '01'):                   # TIM
            APN_SIM = 'ibox.tim.it'
            APN['name']  = 'ibox.tim.it'
        if (MNC_SIM == '10'):                   # Vodafone
            APN_SIM = 'mobile.vodafone.it'
        if (MNC_SIM == '51'):                   # Ho Mobile
            APN_SIM = 'web.ho-mobile.it'      
        if (MNC_SIM == '88'):                   # Wind
            APN_SIM = 'internet.it' 
            APN['name'] = 'internet.it'      
     
    print('APN Setting ...')
    modem.write('AT+CFUN=4', parseError=False)
    modem.write('AT+CGDCONT=1,"IP",' + '"' + APN['name'] + '"', parseError=False)
    time.sleep(2.0)
    modem.write('AT+CFUN=1', parseError=False)
    time.sleep(5.0)
    
    # Tentativo di connessioneINFO
    cnt=0
    while (cnt < 10):
        cnt+=1
        print('Waiting for network coverage...')
        try:
            modem.waitForNetworkCoverage(60)
            break
        except InvalidStateException:
            print('Retry coverage')
    

    NetworkName = "Unknown"
    NetworkName = modem.networkName
    NetworkRAT = "Unknown"
    NetworkRAT = modem.networkRAT

    NetworkInterface = 0
    fsm_status = "IDLE"
    while True:
        if fsm_status == "IDLE":
            try:
                fsm_status = inputimeout(prompt='\r\nWating for acrtion (Digit INFO, MAKE_CALL, CLOSE_CALL or SEND_SMS) --- ESC for Exit \r\n', timeout=10)
            except TimeoutOccurred:
                fsm_status = 'timeout'
        if fsm_status == "MAKE_CALL":
            print('Dialing number: {0}'.format(NUMBER1))
            call = modem.dial(NUMBER1, callStatusUpdateCallbackFunc=callStatusCallback)
            fsm_status = "IDLE" 
        
        elif fsm_status == "CLOSE_CALL":
            print('Forza Chiusura chiamata')
            modem.write('ATH', parseError=False)  
            fsm_status = "IDLE" 
        
        elif fsm_status == "SEND_SMS":
            print('Sending SMS to: {0}'.format(NUMBER1))
            try:
                response = modem.sendSms(NUMBER1, SMS_TEXT, False, 30)
            except CmsError as err:
                print('SEND SMS ERROR: {0} ({1} Error {2})'.format(err, err._description, err.code))
            else:
                if type(response) == SentSms:
                    print('SMS Delivered.')
                else:
                    print('SMS Could not be sent')
            modem.smsTextMode = False
            fsm_status = "IDLE" 
        
        elif fsm_status == "INFO":
            
            NetworkName = modem.networkName
            NetworkRAT = modem.networkRAT
            NetworkSignalStrength = modem.signalStrength
            print('\r\n')
            print(modem.manufacturer)
            print(modem.model)
            print('NetWork:', NetworkName)
            print('RAT: ', RAT_NAME[int(NetworkRAT)])
            print('Signal: ', NetworkSignalStrength) 

            fsm_status = "IDLE"
        elif fsm_status == 'timeout':
            NetworkData = modem.networkDataRegistered
            if NetworkData == '1' or NetworkData == '5': # 1:home ; 5:Roaming 
                if(not NetworkInterface):
                    try: 
                        NetworkInterface = modem.StartNDIS
                    except TimeoutException:
                        print('timeout at command') 
                        
            fsm_status = "IDLE"    
        elif fsm_status == "ESC":
            break
        else:
            print('Command not found .....')
            fsm_status = "IDLE"
    
    modem.close()
    exit()

if __name__ == '__main__':
    main()