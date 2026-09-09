/* Read-only numerical reference adapter to pinned, unmodified RTKLIB.
 * No observations are generated. Input modes: G ECEF; N latitude height
 * elevation fractional day-of-year (2024); S GPS week TOW PRN. */
#include "rtklib.h"
#include <stdarg.h>
int showmsg(char *format, ...) { (void)format; return 0; }
void settspan(gtime_t a,gtime_t b) { (void)a;(void)b; }
void settime(gtime_t a) { (void)a; }
int main(int argc,char **argv) {
    nav_t nav={0}; obs_t obs={0}; sta_t sta={0}; gtime_t zero={0};
    char line[256],mode; double x[3],p[3],az[2]={0},wet,doy,week,tow,prn;
    double year[]={2024,1,1,0,0,0},rs[3],clk,var,dt,best;
    int i,k;
    if(argc==2 && readrnxt(argv[1],1,zero,zero,0,"",&obs,&nav,&sta)<=0) return 2;
    uniqnav(&nav);
    while(fgets(line,sizeof(line),stdin)) {
        mode=line[0];
        if(mode=='G' && sscanf(line+1,"%lf %lf %lf",x,x+1,x+2)==3) {
            ecef2pos(x,p); printf("%.15g %.15g %.15g\n",p[0]*R2D,p[1]*R2D,p[2]);
        } else if(mode=='N' && sscanf(line+1,"%lf %lf %lf %lf",p,p+2,az+1,&doy)==4) {
            p[0]*=D2R;p[1]=0;az[1]*=D2R;
            dt=tropmapf(timeadd(epoch2time(year),(doy-1)*86400),p,az,&wet);
            printf("%.15g %.15g\n",dt,wet);
        } else if(mode=='S' && sscanf(line+1,"%lf %lf %lf",&week,&tow,&prn)==3) {
            gtime_t t=gpst2time((int)week,tow); best=7201;k=-1;
            for(i=0;i<nav.n;i++) if(nav.eph[i].sat==satno(SYS_GPS,(int)prn)) {
                dt=fabs(timediff(nav.eph[i].toe,t));
                if(dt<=best && nav.eph[i].svh==0) {best=dt;k=i;}
            }
            if(k<0) {puts("unavailable");continue;}
            eph2pos(t,&nav.eph[k],rs,&clk,&var);
            printf("%.15g %.15g %.15g\n",rs[0],rs[1],rs[2]);
        } else return 3;
    }
    freeobs(&obs);freenav(&nav,0xFF);return 0;
}
