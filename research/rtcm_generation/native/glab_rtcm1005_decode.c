/*
 * Read-only native RTCM 1005 & CRC-24Q cross-decoder adapter against
 * unmodified ESA / gAGE-UPC gLAB v6.0.0 (/opt/gLAB/source/core/input.c).
 *
 * Calls gLAB's independent C implementations of crc24q(), getMSGtype(),
 * and readMSG1005() directly without sharing any code with NLGCP Python
 * or RTKLIB v2.4.2-p13.
 *
 * Scope honesty: gLAB v6.0.0 supports RTCM 3.x 1004/1005/1006/1008 and
 * does NOT implement MSM4 (1074/1084).  This harness verifies CRC-24Q
 * across all frames and fully decodes RTCM 1005 ECEF ARP fields while
 * reporting non-1005 messages (such as 1074/1084) as CRC-checked only.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "input.h"

int main(int argc, char **argv) {
    if (argc != 2) {
        fprintf(stderr, "usage: %s <rtcm3_file>\n", argv[0]);
        return 2;
    }

    FILE *fp = fopen(argv[1], "rb");
    if (!fp) {
        perror("fopen");
        return 1;
    }

    if (fseek(fp, 0, SEEK_END) != 0) {
        fclose(fp);
        return 1;
    }
    long fsize = ftell(fp);
    if (fsize < 0) {
        fclose(fp);
        return 1;
    }
    rewind(fp);

    unsigned char *buf = (unsigned char *)malloc((size_t)(fsize > 0 ? fsize : 1));
    if (!buf) {
        fclose(fp);
        return 1;
    }
    size_t nread = fread(buf, 1, (size_t)fsize, fp);
    fclose(fp);

    long pos = 0;
    int frame_count = 0;
    int crc_ok_count = 0;
    int crc_fail_count = 0;
    int msg1005_count = 0;
    int msm_unparsed_count = 0;

    printf("{\"decoder\":\"ESA-gAGE-UPC gLAB v6.0.0 input.c\",");
    printf("\"msm4_supported\":false,\"frames\":[");

    while (pos + 6 <= (long)nread) {
        if (buf[pos] != 0xD3) {
            pos++;
            continue;
        }
        int reserved = (buf[pos + 1] >> 2) & 0x3F;
        int payload_len = ((buf[pos + 1] & 0x03) << 8) | buf[pos + 2];
        int total_len = 3 + payload_len + 3;
        if (reserved != 0 || payload_len < 2 || pos + total_len > (long)nread) {
            pos++;
            continue;
        }

        unsigned char *frame = &buf[pos];
        int crc_ok = crc24q(frame, payload_len);
        int msg_type = getMSGtype(frame);

        if (frame_count > 0) {
            printf(",");
        }
        frame_count++;
        if (crc_ok) {
            crc_ok_count++;
        } else {
            crc_fail_count++;
        }

        if (crc_ok && msg_type == 1005 && payload_len >= 19) {
            TMSG1006 st;
            memset(&st, 0, sizeof(st));
            readMSG1005(&st, frame);
            msg1005_count++;
            printf(
                "{\"message_number\":1005,\"payload_length\":%d,"
                "\"crc_ok\":true,\"decoded\":true,"
                "\"station_id\":%u,\"gps_indicator\":%d,"
                "\"glonass_indicator\":%d,\"reference_station_indicator\":%d,"
                "\"oscillator_indicator\":%d,"
                "\"ecef_x_m\":%.4f,\"ecef_y_m\":%.4f,\"ecef_z_m\":%.4f}",
                payload_len,
                st.station_id,
                (st.gps_indicator == '1') ? 1 : 0,
                (st.glonass_indicator == '1') ? 1 : 0,
                (st.referStation_indicator == '1') ? 1 : 0,
                (st.oscillator_indicator == '1') ? 1 : 0,
                st.ecef_x,
                st.ecef_y,
                st.ecef_z
            );
        } else {
            if (msg_type == 1074 || msg_type == 1084) {
                msm_unparsed_count++;
            }
            printf(
                "{\"message_number\":%d,\"payload_length\":%d,"
                "\"crc_ok\":%s,\"decoded\":false,"
                "\"note\":\"%s\"}",
                msg_type,
                payload_len,
                crc_ok ? "true" : "false",
                crc_ok ? "NOT_SUPPORTED_BY_GLAB_V6" : "CRC24Q_FAILED"
            );
        }

        pos += total_len;
    }

    printf(
        "],\"summary\":{\"frame_count\":%d,\"crc_ok_count\":%d,"
        "\"crc_fail_count\":%d,\"msg1005_decoded_count\":%d,"
        "\"msm4_crc_only_count\":%d}}\n",
        frame_count,
        crc_ok_count,
        crc_fail_count,
        msg1005_count,
        msm_unparsed_count
    );

    free(buf);
    return 0;
}
