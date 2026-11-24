import React, { useEffect, useState } from 'react';

const captions = ['Voy, sirpanib ketdim 🫣', 'Hali ushlamadingiz 😜', 'Bu tugma sportchi 🏃',
  'Choyga ham yo‘qmi? ☕', 'Bir piyola gaplashamiz? 😌', 'Kalendar ham kutyapti 📅'];
const anchors = [[25, 19], [75, 19], [25, 81], [75, 81], [50, 17], [50, 83]];
const randomAnchor = () => Math.floor(Math.random() * anchors.length);
function advance(previous) {
  const jump = 1 + Math.floor(Math.random() * (anchors.length - 1));
  return { anchor: (previous.anchor + jump) % anchors.length, turn: previous.turn + 1 };
}

export default function FriendChoice({onYes, onNo}) {
  const [bubble, setBubble] = useState(() => ({anchor: randomAnchor(), turn: 0}));
  useEffect(() => {
    const timer = setInterval(() => {
      if (!document.hidden) setBubble(advance);
    }, 2800);
    return () => clearInterval(timer);
  }, [bubble.turn]);
  const [x,y] = anchors[bubble.anchor];
  return <div className="friend-choice">
    <svg className="friend-thread" aria-hidden="true"><line x1="50%" y1="50%" x2={x+'%'} y2={y+'%'} /></svg>
    <button type="button" className="meeting-action friend-yes" onClick={onYes}>Ha</button>
    <button type="button" className="friend-caption" style={{left:x+'%',top:y+'%'}}
      aria-label="Yo‘q — qochadigan hazil tugmasi" onClick={() => {onNo(); setBubble(advance);}}>
      {captions[bubble.turn % captions.length]}
    </button>
  </div>;
}
