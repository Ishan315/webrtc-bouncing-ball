const video = document.getElementById('remote-video');
const canvas = document.getElementById('tracker-canvas');
const ctx = canvas.getContext('2d', { willReadFrequently: true });
const errorDisplay = document.getElementById('error-display');
const statusDisplay = document.getElementById('status');

let pc = null;
let transport = null;
let stream = null;
let writer = null;
let reader = null;

async function init() {
    try {
        statusDisplay.innerText = "Connecting WebTransport...";
        
        // Hex string of the SHA-256 hash of cert.pem (valid for 13 days)
        const hexHash = "d9977e88dbf7981a87bbebce168ede63270bc1d323799845d8155ef7e2a90470";
        const hashArray = new Uint8Array(hexHash.match(/.{1,2}/g).map(byte => parseInt(byte, 16)));

        const options = {
            serverCertificateHashes: [
                {
                    algorithm: "sha-256",
                    value: hashArray
                }
            ]
        };
        
        transport = new WebTransport(`https://${window.location.hostname}:4433`, options);
        await transport.ready;
        statusDisplay.innerText = "WebTransport Ready. Negotiating WebRTC...";

        // Open a bidirectional stream for signaling and telemetry
        stream = await transport.createBidirectionalStream();
        writer = stream.writable.getWriter();
        reader = stream.readable.getReader();

        // Start the read loop early to handle the incoming answer
        readLoop();

        // Initialize WebRTC
        pc = new RTCPeerConnection({
            iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
        });

        pc.ontrack = (event) => {
            console.log("Received track:", event.track.kind);
            statusDisplay.innerText = "Track received. Starting video...";
            
            const remoteStream = event.streams[0] || new MediaStream([event.track]);
            video.srcObject = remoteStream;
            
            video.onloadedmetadata = () => {
                console.log("Video metadata loaded");
                video.play().catch(e => console.error("Playback failed:", e));
            };
        };

        video.onplaying = () => {
            console.log("Video is playing");
            statusDisplay.innerText = "WebRTC Connected. Tracking Ball...";
            startTracking();
        };

        // Create Offer
        pc.addTransceiver('video', { direction: 'recvonly' });
        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);

        // Send Offer over WebTransport with newline delimiter
        await writer.write(new TextEncoder().encode(JSON.stringify({
            type: 'offer',
            sdp: offer.sdp
        }) + "\n"));

    } catch (e) {
        console.error(e);
        statusDisplay.innerText = "Error: " + e.message;
    }
}

async function readLoop() {
    try {
        let buffer = "";
        const decoder = new TextDecoder();
        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop(); // Keep the last partial line in the buffer

            for (const line of lines) {
                if (line.trim()) {
                    const message = JSON.parse(line);
                    if (message.type === 'error') {
                        errorDisplay.innerText = message.error.toFixed(2);
                    } else if (message.type === 'answer') {
                        // Handle answer if received in the loop
                        await pc.setRemoteDescription(new RTCSessionDescription({
                            type: 'answer',
                            sdp: message.sdp
                        }));
                        statusDisplay.innerText = "WebRTC Connected. Tracking Ball...";
                        startTracking();
                    }
                }
            }
        }
    } catch (e) {
        console.error("Read loop error:", e);
    }
}

function startTracking() {
    const track = () => {
        if (video.videoWidth > 0) {
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
            
            const frame = ctx.getImageData(0, 0, canvas.width, canvas.height);
            const pos = findBall(frame);
            
            if (pos) {
                sendCoordinates(pos.x, pos.y);
            }
        }
        requestAnimationFrame(track);
    };
    track();
}

function findBall(frame) {
    const data = frame.data;
    let sumX = 0;
    let sumY = 0;
    let count = 0;

    // The ball is Red in BGR (server side), which is Red in RGB (client side).
    // Let's look for pixels where Red is high and Blue/Green are low.
    for (let i = 0; i < data.length; i += 4) {
        const r = data[i];
        const g = data[i+1];
        const b = data[i+2];
        
        // Thresholding for red color
        if (r > 150 && g < 100 && b < 100) {
            const x = (i / 4) % frame.width;
            const y = Math.floor((i / 4) / frame.width);
            sumX += x;
            sumY += y;
            count++;
        }
    }

    if (count > 0) {
        return { x: sumX / count, y: sumY / count };
    }
    return null;
}

async function sendCoordinates(x, y) {
    if (writer) {
        await writer.write(new TextEncoder().encode(JSON.stringify({
            type: 'coordinates',
            x: x,
            y: y
        }) + "\n"));
    }
}

init();
