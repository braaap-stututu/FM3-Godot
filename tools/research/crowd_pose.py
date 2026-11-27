"""crowd_pose.py (research, 2026-11-27): poses Photographer_Stand with a dumped animation (Godot/work/crowd_anim, FM3-ReGPU
FM3_ANIM_DUMP=1) on CPU, rotations about crowd_skeleton.py's pivots in model axes, and draws front / side point views.
python tools/research/crowd_pose.py <dir with piv.npy> [plain|conj] [dump name]. Neither quaternion convention put the
camera at the face (2026-11-27): the bone frames are still unknown."""
import sys, struct, numpy as np
sys.path.insert(0,'tools'); import fm3_spectators as sp, fir_read as fr
S=sys.argv[1]; conj=len(sys.argv)>2 and sys.argv[2]=='conj'
PAR=[-1,0,1,2,0,4,5,0,7,8,9,10,7,12,13,14,7]
piv=np.load(S+'/piv.npy')
d=open('../../FM3-files/game/Media/Spectators/models/Photographer_Stand.skinbin','rb').read()
n=struct.unpack_from('>I',d,0x50)[0]; v=np.frombuffer(d[0x54:0x54+n*36], sp.VTX)
P=v['p'].astype(np.float64); b=v['b'].astype(int); b0,b1,w0,w1=b[:,0],b[:,1],b[:,2]/255.0,b[:,3]/255.0
piv[0]=P[b0==0].mean(0)
a=open('../work/crowd_anim/'+(sys.argv[3] if len(sys.argv)>3 else 'A506AEC0')+'.bin','rb').read()
tr,ns=struct.unpack('<II',a[4:12]); o=16+64+256+256; Q=[]
for i in range(ns):
    o+=4; Q.append(np.frombuffer(a[o:o+tr*48],'>f4').reshape(tr,12)); o+=tr*48
Q=np.array(Q)
ang=np.linalg.norm(Q[:,:,0:3],axis=2).sum(1); print('angle sum by tenths', [round(float(x),2) for x in ang[::max(1,ns//10)]]); f=int(ang[:-2].argmax())
def qm(q):
    x,y,z,w=q
    if conj: x,y,z=-x,-y,-z
    return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
G=[None]*17
for k in range(17):
    R=qm(Q[f,k,0:4]); M=np.eye(4); M[:3,:3]=R; M[:3,3]=piv[k]-R@piv[k]
    G[k]=M if PAR[k]<0 else G[PAR[k]]@M
Ph=np.c_[P,np.ones(len(P))]
X=np.zeros_like(P)
for i in range(len(P)):
    X[i]=(w0[i]*(G[b0[i]]@Ph[i])+w1[i]*(G[b1[i]]@Ph[i]))[:3]/max(w0[i]+w1[i],1e-6)
def plot(pts, ax0, ax1, W=420,H=460):
    img=np.zeros((H,W,4),np.uint8); img[...,3]=255; img[...,:3]=30
    u=((pts[:,ax0]+0.6)/1.2*W).astype(int); vv=(H-1-(pts[:,1]+0.1)/2.0*H).astype(int)
    ok=(u>=1)&(u<W-1)&(vv>=1)&(vv<H-1)
    for dy in (0,1):
        for dx in (0,1): img[vv[ok]+dy,u[ok]+dx,:3]=220
    return img
A=np.concatenate([plot(P,0,1),plot(X,0,1),plot(P,2,1),plot(X,2,1)],axis=1)
fr.write_png(S+'/pose%s_%s.png'%('_conj' if conj else '', sys.argv[3] if len(sys.argv)>3 else 'photo'),A.shape[1],A.shape[0],np.ascontiguousarray(A).tobytes())
print('frame',f,'of',ns)
