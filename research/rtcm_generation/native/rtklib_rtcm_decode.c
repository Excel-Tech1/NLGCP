/* Read-only independent RTCM 3.x decoder adapter to unmodified RTKLIB v2.4.2-p13.
 *
 * Usage:
 *   rtklib_rtcm_decode <rtcm_file> <ref_yyyy> <ref_mm> <ref_dd> <ref_hh> <ref_mi> <ref_ss>
 *                      [--glo-fcn <slot:fcn> ...]
 *
 * Feeds raw bytes from <rtcm_file> into unmodified RTKLIB input_rtcm3() and
 * emits a deterministic JSON report on stdout.  Optional --glo-fcn flags seed
 * synthetic test-only GLONASS frequency channel numbers in rtcm.nav.geph so
 * 1084 fine phase-range decoding can be checked separately from standalone 1084.
 */
#include "rtklib.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int showmsg(char *format, ...) { (void)format; return 0; }
void settspan(gtime_t ts, gtime_t te) { (void)ts; (void)te; }
void settime(gtime_t time) { (void)time; }

static void print_json_str(const char *s)
{
    putchar('"');
    for (; *s; s++) {
        unsigned char c = (unsigned char)*s;
        if (c == '"' || c == '\\') {
            putchar('\\');
            putchar(c);
        } else if (c >= 0x20 && c < 0x7f) {
            putchar(c);
        } else {
            printf("\\u%04x", c);
        }
    }
    putchar('"');
}

static const char *sys_name(int sys)
{
    switch (sys) {
        case SYS_GPS: return "GPS";
        case SYS_GLO: return "GLONASS";
        case SYS_GAL: return "GALILEO";
        case SYS_QZS: return "QZSS";
        case SYS_SBS: return "SBAS";
        case SYS_CMP: return "BDS";
        default:      return "UNKNOWN";
    }
}

int main(int argc, char **argv)
{
    rtcm_t rtcm;
    double ep[6];
    FILE *fp;
    int ch, i, j, k, ret, week = 0;
    double tow = 0.0;
    int event_count = 0;
    int crc_errors = 0;
    int decode_errors = 0;
    int total_bytes = 0;

    if (argc < 8) {
        fprintf(stderr, "usage: rtklib_rtcm_decode <file> Y M D h m s [--glo-fcn slot:fcn ...]\n");
        return 2;
    }
    for (i = 0; i < 6; i++) {
        ep[i] = atof(argv[2 + i]);
    }
    if (!init_rtcm(&rtcm)) {
        fprintf(stderr, "init_rtcm failed\n");
        return 3;
    }
    rtcm.time = epoch2time(ep);
    rtcm.outtype = 1;

    for (i = 8; i < argc; i++) {
        if (strcmp(argv[i], "--glo-fcn") == 0 && i + 1 < argc) {
            int slot = 0, fcn = 0;
            if (sscanf(argv[++i], "%d:%d", &slot, &fcn) != 2 ||
                slot < 1 || slot > MAXPRNGLO || fcn < -7 || fcn > 6) {
                fprintf(stderr, "invalid --glo-fcn argument\n");
                free_rtcm(&rtcm);
                return 2;
            }
            rtcm.nav.geph[slot - 1].sat = satno(SYS_GLO, slot);
            rtcm.nav.geph[slot - 1].frq = fcn;
        } else {
            fprintf(stderr, "unexpected argument: %s\n", argv[i]);
            free_rtcm(&rtcm);
            return 2;
        }
    }

    fp = fopen(argv[1], "rb");
    if (!fp) {
        fprintf(stderr, "failed to open input file\n");
        free_rtcm(&rtcm);
        return 4;
    }

    printf("{\"events\":[");
    while ((ch = fgetc(fp)) != EOF) {
        int prev_nbyte = rtcm.nbyte;
        unsigned char byte = (unsigned char)ch;
        total_bytes++;
        rtcm.msgtype[0] = '\0';
        ret = input_rtcm3(&rtcm, byte);

        /* Detect end of an RTCM3 frame attempt (nbyte reset to 0 after buffering >= 3 bytes). */
        if (prev_nbyte >= 2 && rtcm.nbyte == 0) {
            int crc_ok = (rtcm.len >= 3) &&
                (rtk_crc24q(rtcm.buff, rtcm.len) == getbitu(rtcm.buff, rtcm.len * 8, 24));
            int msg_no = (crc_ok && rtcm.len >= 5) ? (int)getbitu(rtcm.buff, 24, 12) : -1;
            if (!crc_ok) crc_errors++;
            if (ret < 0) decode_errors++;
            tow = time2gpst(rtcm.time, &week);

            if (event_count > 0) putchar(',');
            event_count++;
            printf("{\"ret\":%d,\"crc_ok\":%s,\"msg_no\":%d,\"frame_len\":%d,",
                   ret, crc_ok ? "true" : "false", msg_no, rtcm.len + 3);
            printf("\"staid\":%d,\"itrf\":%d,\"pos_ecef\":[%.6f,%.6f,%.6f],",
                   rtcm.staid, rtcm.sta.itrf,
                   rtcm.sta.pos[0], rtcm.sta.pos[1], rtcm.sta.pos[2]);
            printf("\"gps_week\":%d,\"gps_tow_s\":%.6f,\"obsflag\":%d,",
                   week, tow, rtcm.obsflag);
            printf("\"msgtype\":"); print_json_str(rtcm.msgtype);
            printf(",\"msmtype_gps\":"); print_json_str(rtcm.msmtype[0]);
            printf(",\"msmtype_glo\":"); print_json_str(rtcm.msmtype[1]);
            printf(",\"obs\":[");
            k = 0;
            if (ret == 1 || (ret == 0 && crc_ok && (msg_no == 1074 || msg_no == 1084))) {
                for (i = 0; i < rtcm.obs.n; i++) {
                    obsd_t *d = &rtcm.obs.data[i];
                    int prn = 0;
                    int sys = satsys(d->sat, &prn);
                    for (j = 0; j < NFREQ + NEXOBS; j++) {
                        int freq = 0;
                        char *code_str;
                        if (d->code[j] == CODE_NONE && d->P[j] == 0.0 && d->L[j] == 0.0) {
                            continue;
                        }
                        code_str = code2obs(d->code[j], &freq);
                        if (k > 0) putchar(',');
                        k++;
                        printf("{\"sys\":"); print_json_str(sys_name(sys));
                        printf(",\"prn\":%d,\"code\":", prn);
                        print_json_str(code_str ? code_str : "");
                        printf(",\"freq\":%d,\"P_m\":%.6f,\"L_cyc\":%.6f,"
                               "\"SNR_dbhz\":%.2f,\"LLI\":%u}",
                               freq, d->P[j], d->L[j],
                               (double)d->SNR[j] * 0.25, (unsigned int)d->LLI[j]);
                    }
                }
            }
            printf("]}");
        }
    }
    fclose(fp);

    printf("],\"summary\":{\"total_bytes\":%d,\"events\":%d,\"crc_errors\":%d,"
           "\"decode_errors\":%d,\"nmsg3_1005\":%u,\"nmsg3_1074\":%u,"
           "\"nmsg3_1084\":%u,\"nmsg3_other\":%u,\"trailing_nbyte\":%d}}\n",
           total_bytes, event_count, crc_errors, decode_errors,
           rtcm.nmsg3[5], rtcm.nmsg3[74], rtcm.nmsg3[84], rtcm.nmsg3[0],
           rtcm.nbyte);

    free_rtcm(&rtcm);
    return 0;
}
