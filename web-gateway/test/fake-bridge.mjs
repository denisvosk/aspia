// Test double for the native process protocol, never included in the deployable package.
import { createInterface } from 'node:readline';
const png = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGOQDEgBAAFTAM4KP2oUAAAAAElFTkSuQmCC';
const lines = createInterface({input:process.stdin});
lines.on('line', line => {
  const c=JSON.parse(line);
  if(c.type==='connect')console.log(JSON.stringify({type:'status',state:'connected'}));
  if(c.type==='frame')console.log(JSON.stringify({type:'frame',png,width:1,height:1,screenWidth:1920,screenHeight:1080}));
  if(c.type==='stop')process.exit(0);
});
lines.on('close',()=>process.exit(0));
