export function getApiUrl() {
  const url =
    process.env.NEXT_PUBLIC_API_URL ||
    process.env.NEXT_PUBLIC_FLY_API_URL ||
    "https://polymarket-bots-farzad.fly.dev"

  return url.replace(/\/$/, "")
}

export function getWsUrl() {
  const apiUrl = getApiUrl()
  const wsUrl = apiUrl.replace(/^http(s)?:\/\//, (m) => (m === "https://" ? "wss://" : "ws://"))
  return wsUrl
}

