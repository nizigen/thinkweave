const MOJIBAKE_PATTERN = /[ÃÂâæçðï�]/;

function countCjk(text) {
  const matched = String(text || '').match(/[\u4e00-\u9fff]/g);
  return matched ? matched.length : 0;
}

function countSuspicious(text) {
  const matched = String(text || '').match(/[ÃÂâæçðï�]/g);
  return matched ? matched.length : 0;
}

function decodeUtf8FromLatin1View(text) {
  const source = String(text || '');
  const bytes = Uint8Array.from(Array.from(source).map((ch) => ch.charCodeAt(0) & 0xff));
  return new TextDecoder('utf-8').decode(bytes);
}

export function normalizeDisplayText(value) {
  const source = String(value || '');
  if (!source || !MOJIBAKE_PATTERN.test(source)) return source;

  try {
    const decoded = decodeUtf8FromLatin1View(source);
    if (!decoded || decoded.includes('\uFFFD')) return source;

    const sourceScore = countCjk(source) * 3 - countSuspicious(source);
    const decodedScore = countCjk(decoded) * 3 - countSuspicious(decoded);
    return decodedScore > sourceScore ? decoded : source;
  } catch {
    return source;
  }
}
