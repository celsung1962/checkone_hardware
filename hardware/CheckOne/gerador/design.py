# Definição única do circuito do CheckOne (v1). Cada componente: ref, símbolo, valor,
# footprint, LCSC, folha e ligações {pino: rede}. Gera esquemático e placa.
R0603='Resistor_SMD:R_0603_1608Metric'; C0603='Capacitor_SMD:C_0603_1608Metric'; C0805='Capacitor_SMD:C_0805_2012Metric'
parts=[]
def P(ref,sym,val,fp,lcsc,sheet,pins,dnp=False,grp=None):
    parts.append(dict(ref=ref,sym=sym,val=val,fp=fp,lcsc=lcsc,sheet=sheet,pins=pins,dnp=dnp,grp=grp))
R=lambda ref,val,lcsc,a,b,sheet,fp=R0603,grp=None: P(ref,'Device:R',val,fp,lcsc,sheet,{'1':a,'2':b},grp=grp)
C=lambda ref,val,lcsc,a,b,sheet,fp=C0603,grp=None: P(ref,'Device:C',val,fp,lcsc,sheet,{'1':a,'2':b},grp=grp)
CP=lambda ref,pos,neg,sheet,grp=None: P(ref,'Device:C_Polarized','220uF/50V','Capacitor_SMD:CP_Elec_10x10.5','C46550417',sheet,{'1':pos,'2':neg},grp=grp)
S='alimentacao'
# ---------------- Alimentação ----------------
P('J1','Connector:Barrel_Jack_Switch','DC-005-A200','CheckOne:DC-005-A200','C720557',S,{'1':'VIN_RAW','2':'GND','3':'GND'},grp='dc')
P('F1','Device:Polyfuse','1812L160/30GR','Fuse:Fuse_1812_4532Metric','C18198337',S,{'1':'VIN_RAW','2':'VIN_F'},grp='in')
P('D1','Device:D_Zener','SMBJ24A','Diode_SMD:D_SMB','C19077578',S,{'1':'VIN_F','2':'GND'},grp='in')
P('D2','Device:D_Schottky','SS34','Diode_SMD:D_SMA','C8678',S,{'1':'VIN_S','2':'VIN_F'},grp='in')
C('C1','100nF','C14663','VIN_S','GND',S,grp='in')
R('R1','10k','C25804','VIN_S','LED24_A',S,grp='led'); P('LED1','Device:LED','KT-0805G verde','LED_SMD:LED_0805_2012Metric','C2297',S,{'2':'LED24_A','1':'GND'},grp='led')
# partida suave
P('Q1','CheckOne:AO4485','AO4485','Package_SO:SOIC-8_3.9x4.9mm_P1.27mm','C5334068',S,{'1':'VIN_S','2':'VIN_S','3':'VIN_S','4':'SS_G','5':'V24_D','6':'V24_D','7':'V24_D','8':'V24_D'},grp='ss')
R('R2','4.7k','C23162','VIN_S','SS_G',S,grp='ss'); R('R3','10k','C25804','SS_G','GND',S,grp='ss')
CP('C2','VIN_S','SS_G',S,grp='ss')
R('R4','1k','C21190','SS_G','SS_CGD',S,grp='ss')
C('C3','1uF','C28323','SS_CGD','V24_D',S,C0805,grp='ss'); C('C4','1uF','C28323','SS_CGD','V24_D',S,C0805,grp='ss')
# filtro pi
CP('C5','V24_D','GND',S,grp='flt'); C('C6','1uF','C28323','V24_D','GND',S,C0805,grp='flt')
P('L1','Device:L','68uH FCH1040','Inductor_SMD:L_10.4x10.4_H4.8','C20415548',S,{'1':'V24_D','2':'V24_F'},grp='flt')
CP('C7','V24_F','GND',S,grp='flt'); C('C8','1uF','C28323','V24_F','GND',S,C0805,grp='flt'); C('C9','100nF','C14663','V24_F','GND',S,grp='flt')
# buck 5 V
P('U1','CheckOne:XL1509-5.0','XL1509-5.0E1','Package_SO:SOIC-8_3.9x4.9mm_P1.27mm','C61063',S,{'1':'V24_F','2':'BUCK_SW','3':'+5V','4':'GND','5':'GND','6':'GND','7':'GND','8':'GND'},grp='buck')
CP('C10','V24_F','GND',S,grp='buck'); C('C11','1uF','C28323','V24_F','GND',S,C0805,grp='buck')
P('D3','Device:D_Schottky','SS34','Diode_SMD:D_SMA','C8678',S,{'1':'BUCK_SW','2':'GND'},grp='buck')
P('L2','Device:L','68uH FCH1040','Inductor_SMD:L_10.4x10.4_H4.8','C20415548',S,{'1':'BUCK_SW','2':'+5V'},grp='buck')
CP('C12','+5V','GND',S,grp='buck')
R('R5','1.5k','C22843','+5V','LED5_A',S,grp='led'); P('LED2','Device:LED','KT-0805G verde','LED_SMD:LED_0805_2012Metric','C2297',S,{'2':'LED5_A','1':'GND'},grp='led')
# 5 V do display
P('D4','Device:D_Schottky','SS34','Diode_SMD:D_SMA','C8678',S,{'1':'5V_D','2':'+5V'},grp='disp5')
R('R6','0R (alternativa ao D4)','C21189','+5V','5V_D',S,grp='disp5'); parts[-1]['dnp']=True
P('FB1','Device:FerriteBead_Small','GZ2012D601TF','Inductor_SMD:L_0805_2012Metric','C1017',S,{'1':'5V_D','2':'+5V_DISP'},grp='disp5')
P('FB2','Device:FerriteBead_Small','GZ2012D601TF','Inductor_SMD:L_0805_2012Metric','C1017',S,{'1':'5V_D','2':'+5V_DISP'},grp='disp5')
# INA226 e barramento dos sensores
R('R7','100mR 1% (paralelo c/ R13 = 50 mR)','C25334','V24_F','+24V_SENS',S,'Resistor_SMD:R_1206_3216Metric',grp='ina')
R('R13','100mR 1% (paralelo c/ R7 = 50 mR)','C25334','V24_F','+24V_SENS',S,'Resistor_SMD:R_1206_3216Metric',grp='ina')
P('U2','Sensor_Energy:INA226','INA226AIDGSR','Package_SO:VSSOP-10_3x3mm_P0.5mm','C49851',S,{'1':'GND','2':'GND','3':'NC_ALERT','4':'SDA','5':'SCL','6':'+3V3','7':'GND','8':'+24V_SENS','9':'+24V_SENS','10':'V24_F'},grp='ina')
C('C13','100nF','C14663','+3V3','GND',S,grp='ina')
CP('C14','+24V_SENS','GND',S,grp='ina')
# 3,3 V local
P('U3','Regulator_Linear:XC6206PxxxMR','XC6206P332MR','Package_TO_SOT_SMD:SOT-23','C5446',S,{'1':'GND','2':'+3V3','3':'+5V'},grp='ldo')
C('C15','1uF','C28323','+5V','GND',S,C0805,grp='ldo'); C('C16','1uF','C28323','+3V3','GND',S,C0805,grp='ldo')
R('R8','1k','C21190','+3V3','LED33_A',S,grp='led'); P('LED3','Device:LED','KT-0805G verde','LED_SMD:LED_0805_2012Metric','C2297',S,{'2':'LED33_A','1':'GND'},grp='led')
R('R9','10R','C22859','+3V3','+3V3A',S,grp='ldo'); C('C17','1uF','C28323','+3V3A','GND',S,C0805,grp='ldo')
C('C18','100nF','C14663','+3V3','GND',S,grp='ldo')
R('R10','1k','C21190','DISP_3V3','LED3D_A',S,grp='led'); P('LED4','Device:LED','KT-0805G verde','LED_SMD:LED_0805_2012Metric','C2297',S,{'2':'LED3D_A','1':'GND'},grp='led')
R('R11','4.7k','C23162','+3V3','SDA',S,grp='i2c'); R('R12','4.7k','C23162','+3V3','SCL',S,grp='i2c')
for i,(n,net) in enumerate([('24V','+24V_SENS'),('5V','+5V'),('3V3','+3V3'),('3V3A','+3V3A'),('SDA','SDA'),('SCL','SCL'),('GND','GND'),('GND2','GND')]):
    P(f'TP{i+1}','Connector:TestPoint',n,'TestPoint:TestPoint_Pad_D1.5mm','',S,{'1':net},grp='tp')
# ---------------- Canais ----------------
S='canais'
for n in range(1,9):
    out=f'OUT{n}'; iin=f'IIN{n}'; ain=f'AIN{n}'; a=f'CH{n}_PTC'
    g=f'ch{n}'
    P(f'F1{n}','Device:Polyfuse','JK-SMD0805-020-30V','Fuse:Fuse_0805_2012Metric','C516070',S,{'1':'+24V_SENS','2':a},grp=g)
    P(f'FB1{n}','Device:FerriteBead_Small','GZ2012D601TF','Inductor_SMD:L_0805_2012Metric','C1017',S,{'1':a,'2':out},grp=g)
    C(f'C1{n}0','100nF','C14663',out,'GND',S,grp=g)
    P(f'J1{n}','Connector_Generic:Conn_01x04',f'CH{n} +24/GND/Iin/Iout','CheckOne:KF2EDGRC-5.08-4P','C441238',S,{'1':out,'2':'GND','3':iin,'4':'GND'},grp=g)
    R(f'R1{n}0','120R 0,1%','C870389',iin,'GND',S,'Resistor_SMD:R_1206_3216Metric',grp=g)
    P(f'D1{n}','Device:D_Zener','SMAJ5.0A','Diode_SMD:D_SMA','C2925443',S,{'1':iin,'2':'GND'},grp=g)
    R(f'R1{n}1','1k','C21190',iin,ain,S,grp=g)
    P(f'D2{n}','Diode:BAT54S','BAT54S','Package_TO_SOT_SMD:SOT-23','C7420333',S,{'1':'GND','2':'+3V3A','3':ain},grp=g)
    C(f'C1{n}1','10nF','C57112',ain,'GND',S,grp=g)
# ---------------- ADCs e NTC ----------------
S='adcs'
P('U4','Analog_ADC:ADS1115IDGS','ADS1115 (0x48)','Package_SO:VSSOP-10_3x3mm_P0.5mm','C37593',S,{'1':'GND','2':'NC_A4','3':'GND','4':'AIN1','5':'AIN2','6':'AIN3','7':'AIN4','8':'+3V3A','9':'SDA','10':'SCL'},grp='ads1')
P('U5','Analog_ADC:ADS1115IDGS','ADS1115 (0x49)','Package_SO:VSSOP-10_3x3mm_P0.5mm','C37593',S,{'1':'+3V3A','2':'NC_A5','3':'GND','4':'AIN5','5':'AIN6','6':'AIN7','7':'AIN8','8':'+3V3A','9':'SDA','10':'SCL'},grp='ads2')
P('U6','Analog_ADC:ADS1115IDGS','ADS1115 (0x4A)','Package_SO:VSSOP-10_3x3mm_P0.5mm','C37593',S,{'1':'SDA','2':'NC_A6','3':'GND','4':'NTC1_ADC','5':'+3V3A','6':'NTC2_ADC','7':'GND','8':'+3V3A','9':'SDA','10':'SCL'},grp='ads3')
C('C40','100nF','C14663','+3V3A','GND',S,grp='ads1'); C('C41','100nF','C14663','+3V3A','GND',S,grp='ads2'); C('C42','100nF','C14663','+3V3A','GND',S,grp='ads3')
for k,(j,g) in enumerate([('J2','ntc1'),('J3','ntc2')]):
    node=f'NTC{k+1}'; adc=f'NTC{k+1}_ADC'
    P(j,'Connector_Generic:Conn_01x02',f'NTC{k+1} (XH)','Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical','C158012',S,{'1':node,'2':'GND'},grp=g)
    R(f'R4{k}0','10k','C25804','+3V3A',node,S,grp=g)
    C(f'C4{k}3','1uF','C28323',node,'GND',S,C0805,grp=g)
    R(f'R4{k}1','1k','C21190',node,adc,S,grp=g)
    P(f'D4{k}','Diode:BAT54S','BAT54S','Package_TO_SOT_SMD:SOT-23','C7420333',S,{'1':'GND','2':'+3V3A','3':adc},grp=g)
    C(f'C4{k}4','10nF','C57112',adc,'GND',S,grp=g)
# ---------------- Display e RTC ----------------
S='display_rtc'
P('J4','Connector_Generic:Conn_01x04','DISPLAY 5V (P1)','Connector_Molex:Molex_PicoBlade_53398-0471_1x04-1MP_P1.25mm_Vertical','C668611',S,{'1':'+5V_DISP','2':'NC_TX','3':'NC_RX','4':'GND'},grp='jpwr')
P('J5','Connector_Generic:Conn_01x04','I2C CYD (CN1)','Connector_Molex:Molex_PicoBlade_53398-0471_1x04-1MP_P1.25mm_Vertical','C668611',S,{'1':'GND','2':'SCL','3':'SDA','4':'DISP_3V3'},grp='ji2c')
P('J6','Connector_Generic:Conn_01x04','I2C JC3248 (P4)','Connector_Molex:Molex_PicoBlade_53398-0471_1x04-1MP_P1.25mm_Vertical','C668611',S,{'1':'GND','2':'DISP_3V3','3':'SDA','4':'SCL'},grp='ji2c')
P('J7','Connector_Generic:Conn_01x04','DISPLAY EXT (JC4880)','Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical','C2691448',S,{'1':'+5V_DISP','2':'GND','3':'SDA','4':'SCL'},grp='jext')
P('U7','Timer_RTC:PCF8563T','PCF8563T','Package_SO:SOIC-8_3.9x4.9mm_P1.27mm','C7440',S,{'1':'OSCI','2':'OSCO','3':'NC_INT','4':'GND','5':'SDA','6':'SCL','7':'NC_CLKO','8':'VRTC'},grp='rtc')
P('Y1','Device:Crystal','32.768kHz 12.5pF','Crystal:Crystal_SMD_3215-2Pin_3.2x1.5mm','C32346',S,{'1':'OSCI','2':'OSCO'},grp='rtc')
C('C50','22pF C0G','C1653','OSCI','GND',S,grp='rtc'); C('C51','100nF','C14663','VRTC','GND',S,grp='rtc')
P('D50','Diode:BAT54W','BAT54W','Package_TO_SOT_SMD:SOT-323_SC-70','C7502705',S,{'1':'+3V3','2':'NC_D50','3':'VRTC'},grp='rtc')
P('D51','Diode:BAT54W','BAT54W','Package_TO_SOT_SMD:SOT-323_SC-70','C7502705',S,{'1':'VBAT','2':'NC_D51','3':'VRTC'},grp='rtc')
P('BT1','Device:Battery_Cell','CR2032 (BS-02-A1AJ006)','CheckOne:BS-02-A1AJ006','C964745',S,{'1':'VBAT','2':'GND'},grp='bat')
for i in range(4): P(f'H{i+1}','Mechanical:MountingHole','M3 placa','MountingHole:MountingHole_3.2mm_M3','',S,{},grp='mh')
for i in range(4): P(f'H{i+5}','Mechanical:MountingHole','M3 espaçador CYD','MountingHole:MountingHole_3.2mm_M3','',S,{},grp='mh')
