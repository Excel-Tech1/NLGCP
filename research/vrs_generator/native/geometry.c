/* Offline adapter to unmodified RTKLIB v2.4.2-p13. No observation fabrication.
 * Input: GPST calendar fields, GPS PRN, observed anchor pseudorange (metres).
 * Output: ranges, clock translation, satellite ECEF, elevations. See theory doc.
 */
#include "rtklib.h"
#include <stdarg.h>

int showmsg(char *format, ...) { (void)format; return 0; }
void settspan(gtime_t ts, gtime_t te) { (void)ts; (void)te; }
void settime(gtime_t time) { (void)time; }

int main(int argc, char **argv)
{
    nav_t nav = {0};
    obs_t obs = {0};
    sta_t sta = {0};
    gtime_t zero = {0}, rx;
    obsd_t measurement = {0};
    double a[3], v[3], pa[3], pv[3], ep[6], p, ra, rv, prev;
    double rsa[6], rsv[6], ca[2], cv[2], var, e[3], azela[2], azelv[2];
    int i, prn, sat, health, status;
    char line[256];
    if (argc != 8) return 2;
    for (i=0;i<3;i++) { a[i]=atof(argv[2+i]); v[i]=atof(argv[5+i]); }
    ecef2pos(a,pa); ecef2pos(v,pv);
    if (readrnxt(argv[1],1,zero,zero,0.0,"",&obs,&nav,&sta)<=0 || nav.n==0) return 3;
    uniqnav(&nav);
    while (fgets(line,sizeof(line),stdin)) {
        if (sscanf(line,"%lf %lf %lf %lf %lf %lf %d %lf",ep,ep+1,ep+2,
                   ep+3,ep+4,ep+5,&prn,&p)!=8) return 4;
        status=0; sat=satno(SYS_GPS,prn); rx=epoch2time(ep);
        measurement.time=rx; measurement.sat=sat; measurement.P[0]=p;
        if (!sat || !isfinite(p) || p<=0.0) status=1;
        if (!status) {
            satposs(rx,&measurement,1,&nav,EPHOPT_BRDC,rsa,ca,&var,&health);
            if (health!=0 || norm(rsa,3)<=RE_WGS84) status=1;
        }
        if (!status) {
            ra=geodist(rsa,a,e); satazel(pa,e,azela);
            rv=geodist(rsa,v,e); cv[0]=ca[0];
            /* Same reception instant, target-specific transmit time. Fixed-point
             * light-time shift uses geometric differences; anchor atmosphere,
             * code biases and clock datum remain inherited. */
            for (i=0;i<8;i++) {
                prev=rv;
                measurement.P[0]=p+(rv-ra)-CLIGHT*(cv[0]-ca[0]);
                satposs(rx,&measurement,1,&nav,EPHOPT_BRDC,rsv,cv,&var,&health);
                if (health!=0 || norm(rsv,3)<=RE_WGS84) {
                    status=1; break;
                }
                rv=geodist(rsv,v,e);
                if (fabs(rv-prev)<1E-5) break;
            }
            if (i==8 || ra<=0 || rv<=0) status=2;
            satazel(pv,e,azelv);
        }
        if (status) { printf("%d\n",status); continue; }
        printf("0 %.12f %.12f %.12f %.12f %.12f %.12f %.12f %.12f %.12f %.12f %.12f\n",
               ra,rv,-CLIGHT*(cv[0]-ca[0]),rsa[0],rsa[1],rsa[2],
               rsv[0],rsv[1],rsv[2],azela[1]*R2D,azelv[1]*R2D);
    }
    freeobs(&obs); freenav(&nav,0xFF);
    return 0;
}
