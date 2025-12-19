// Modbus (plain) -> MMS write (libiec61850) -> relay_mirror.json for dashboard
// Relay IP fixed to: 192.168.1.21
 
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <time.h>
#include <errno.h>
 
#include <modbus/modbus.h>
#include <libiec61850/iec61850_client.h>
 
#define MODBUS_HOST "127.0.0.1"
#define MODBUS_PORT 1502
#define MODBUS_UNIT 1
 
#define RELAY_IP    "192.168.1.21"
#define RELAY_PORT  102
 
#define SCALE 10.0f
#define MIRROR_FILE "relay_mirror.json"
 
// MMS attribute paths (adjust only if your relay uses different refs)
#define REF_PAC   "LD0/MMXU1.TotW.mag.f"
#define REF_PDC   "LD0/MMXU1.TotWDC.mag.f"
#define REF_VDC   "LD0/MMXU1.VolDC.mag.f"
#define REF_IDC   "LD0/MMXU1.AmpDC.mag.f"
#define REF_G     "LD0/MET1.Irradiance.mag.f"
#define REF_TCELL "LD0/MET1.CellTemp.mag.f"
 
/* For measured values (.mag.f), MX is typically correct */
#ifndef IEC61850_FC_MX
/* If your headers use a different name, change this single define accordingly */
#define IEC61850_FC_MX MX
#endif
 
static void iso_ts(char* buf, size_t n)
{
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    struct tm tm;
    localtime_r(&ts.tv_sec, &tm);
    snprintf(buf, n, "%04d-%02d-%02dT%02d:%02d:%02d",
             tm.tm_year + 1900, tm.tm_mon + 1, tm.tm_mday,
             tm.tm_hour, tm.tm_min, tm.tm_sec);
}
 
static int write_mirror(const char* ts,
                        int mms_ok,
                        const char* mms_err,
                        float pac, float pdc, float vdc, float idc, float g, float tcell)
{
    FILE* f = fopen(MIRROR_FILE, "w");
    if (!f) return -1;
 
    char errbuf[256];
    errbuf[0] = '\0';
    if (mms_err && mms_err[0]) {
        size_t j = 0;
        for (size_t i = 0; mms_err[i] && j + 2 < sizeof(errbuf); i++) {
            if (mms_err[i] == '\"') { errbuf[j++] = '\''; }
            else if (mms_err[i] == '\n' || mms_err[i] == '\r') { errbuf[j++] = ' '; }
            else { errbuf[j++] = mms_err[i]; }
        }
        errbuf[j] = '\0';
    }
 
    fprintf(f,
        "{\n"
        "  \"ts\": \"%s\",\n"
        "  \"mms_ok\": %s,\n"
        "  \"mms_error\": \"%s\",\n"
        "  \"P_ac_W\": %.3f,\n"
        "  \"P_dc_W\": %.3f,\n"
        "  \"V_dc_V\": %.3f,\n"
        "  \"I_dc_A\": %.3f,\n"
        "  \"G_poa_Wm2\": %.3f,\n"
        "  \"T_cell_C\": %.3f\n"
        "}\n",
        ts,
        mms_ok ? "true" : "false",
        errbuf,
        pac, pdc, vdc, idc, g, tcell
    );
 
    fclose(f);
    return 0;
}
 
static int ensure_mms_connected(IedConnection con, IedClientError* err)
{
    if (IedConnection_getState(con) == IED_STATE_CONNECTED)
        return 1;
 
    IedConnection_connect(con, err, RELAY_IP, RELAY_PORT);
    if (*err != IED_ERROR_OK)
        return 0;
 
    return (IedConnection_getState(con) == IED_STATE_CONNECTED);
}
 
static int mms_write_float_mx(IedConnection con, IedClientError* err,
                             const char* ref, float v,
                             char* emsg, size_t emsg_n)
{
    *err = IED_ERROR_OK;
    IedConnection_writeFloatValue(con, err, ref, IEC61850_FC_MX, v);
 
    if (*err != IED_ERROR_OK) {
        snprintf(emsg, emsg_n, "write %s FC=MX err=%d", ref, *err);
        return 0;
    }
    return 1;
}
 
int main(void)
{
    modbus_t* mb = NULL;
    IedConnection con = NULL;
    IedClientError err = IED_ERROR_OK;
 
    mb = modbus_new_tcp(MODBUS_HOST, MODBUS_PORT);
    if (!mb) {
        fprintf(stderr, "modbus_new_tcp failed\n");
        return 1;
    }
 
    modbus_set_slave(mb, MODBUS_UNIT);
 
    if (modbus_connect(mb) == -1) {
        fprintf(stderr, "modbus_connect failed: %s\n", modbus_strerror(errno));
        modbus_free(mb);
        return 1;
    }
 
    con = IedConnection_create();
    if (!ensure_mms_connected(con, &err)) {
        fprintf(stderr, "MMS connect failed initially (will keep trying): err=%d\n", err);
    }
 
    printf("Bridge running:\n");
    printf("  Modbus: %s:%d (unit %d)\n", MODBUS_HOST, MODBUS_PORT, MODBUS_UNIT);
    printf("  MMS:    %s:%d\n", RELAY_IP, RELAY_PORT);
    printf("  Mirror: %s\n", MIRROR_FILE);
 
    while (1) {
        uint16_t regs[6];
        int rc = modbus_read_registers(mb, 0, 6, regs);
        if (rc != 6) {
            fprintf(stderr, "modbus_read_registers failed: %s\n", modbus_strerror(errno));
            sleep(1);
            continue;
        }
 
        float pac   = ((float) regs[0]) / SCALE;
        float pdc   = ((float) regs[1]) / SCALE;
        float vdc   = ((float) regs[2]) / SCALE;
        float idc   = ((float) regs[3]) / SCALE;
        float g     = ((float) regs[4]) / SCALE;
        float tcell = ((float) regs[5]) / SCALE;
 
        char ts[64];
        iso_ts(ts, sizeof(ts));
 
        int mms_ok = 1;
        char mms_err[256]; mms_err[0] = '\0';
 
        if (!ensure_mms_connected(con, &err)) {
            mms_ok = 0;
            snprintf(mms_err, sizeof(mms_err), "connect err=%d", err);
        }
 
        if (mms_ok) {
            if (!mms_write_float_mx(con, &err, REF_PAC, pac,   mms_err, sizeof(mms_err))) mms_ok = 0;
            if (mms_ok && !mms_write_float_mx(con, &err, REF_PDC, pdc,   mms_err, sizeof(mms_err))) mms_ok = 0;
            if (mms_ok && !mms_write_float_mx(con, &err, REF_VDC, vdc,   mms_err, sizeof(mms_err))) mms_ok = 0;
            if (mms_ok && !mms_write_float_mx(con, &err, REF_IDC, idc,   mms_err, sizeof(mms_err))) mms_ok = 0;
            if (mms_ok && !mms_write_float_mx(con, &err, REF_G,   g,     mms_err, sizeof(mms_err))) mms_ok = 0;
            if (mms_ok && !mms_write_float_mx(con, &err, REF_TCELL, tcell, mms_err, sizeof(mms_err))) mms_ok = 0;
        }
 
        write_mirror(ts, mms_ok, mms_err, pac, pdc, vdc, idc, g, tcell);
 
        usleep(200 * 1000); // 200ms loop
    }
 
    modbus_close(mb);
    modbus_free(mb);
    IedConnection_destroy(con);
    return 0;
}