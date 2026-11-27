"""crowd_skeleton.py (research, 2026-11-27): the standing crowd skeleton: hierarchy from the anim files' bone names
(root, legL/R upper-lower-foot, spine, armL/R shoulder-upper-lower-hand, head), joint pivots from the vertices two bones
share in Photographer_Stand.skinbin. Run from frame-ir: python tools/research/crowd_skeleton.py <out dir> (writes piv.npy)."""
import sys, os, struct, numpy as np
sys.path.insert(0,'tools'); import fm3_spectators as sp, fir_read as fr
NAMES=['root','legL_upper','legL_lower','legL_foot','legR_upper','legR_lower','legR_foot','spine','armL_shoulder','armL_upper','armL_lower','armL_hand','armR_shoulder','armR_upper','armR_lower','armR_hand','head']
PAR=[-1,0,1,2,0,4,5,0,7,8,9,10,7,12,13,14,7]
src='../../FM3-files/game/Media/Spectators/models/'
d=open(src+'Photographer_Stand.skinbin','rb').read()
n=struct.unpack_from('>I',d,0x50)[0]; v=np.frombuffer(d[0x54:0x54+n*36], sp.VTX)
P=v['p'].astype(np.float64); b=v['b'].astype(int); b0,b1,w0,w1=b[:,0],b[:,1],b[:,2]/255.0,b[:,3]/255.0
print('bones used', sorted(set(b0)|set(b1[w1>0])))
piv=np.zeros((17,3))
for k in range(17):
    p=PAR[k]
    if p<0:
        m=(b0==k); piv[k]=P[m].mean(0) if m.any() else 0; continue
    shared=((b0==k)&(b1==p)&(w1>0))|((b0==p)&(b1==k)&(w1>0))
    if shared.sum()>=3: piv[k]=P[shared].mean(0); src_='shared %d'%shared.sum()
    else:
        mk=P[(b0==k)&(w0>0.99)]; mp=P[(b0==p)&(w0>0.99)]
        # nearest points between the two clusters
        if len(mk) and len(mp):
            dd=((mk[:,None,:]-mp[None,:,:])**2).sum(2); i,j=np.unravel_index(dd.argmin(),dd.shape); piv[k]=(mk[i]+mp[j])/2; src_='nearest'
        else: src_='none'
    print('%-14s parent %-14s pivot %s (%s)'%(NAMES[k], NAMES[p] if p>=0 else '-', piv[k].round(3), src_))
np.save(sys.argv[1]+'/piv.npy', piv)
