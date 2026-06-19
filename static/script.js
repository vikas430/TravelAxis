const peopleSelect = document.getElementById("people");
const splitBtn = document.getElementById("split-btn");
const totalExpenseEl = document.getElementById("total-expense");
const peopleCountEl = document.getElementById("people-count");
const perPersonEl = document.getElementById("per-person");
const startingPointInput = document.getElementById("starting_point");
const destinationInput = document.getElementById("destination");
const budgetSelect = document.getElementById("budget");
const chatWindow = document.getElementById("chat-window");
const chatText = document.getElementById("chat-text");
const sendBtn = document.getElementById("send-btn");
const replyButtons = document.querySelectorAll(".reply-btn");
const menuLinks = document.querySelectorAll(".menu-link");
const actionOutput = document.getElementById("action-output");
const hotelSelectButtons = document.querySelectorAll(".hotel-select-btn");
const tripForm = document.querySelector(".trip-form");
const routeNameEl = document.getElementById("route-name");
const routeDistanceEl = document.getElementById("route-distance");
const distanceSourceEl = document.getElementById("distance-source");
const startPlaceEl = document.getElementById("start-place");
const destinationPlaceEl = document.getElementById("destination-place");
const googleMapEl = document.getElementById("google-map");
const fallbackMapEl = document.getElementById("fallback-map");
const mapFallbackEl = document.getElementById("map-fallback");
const mapDistancePillEl = document.getElementById("map-distance-pill");
const hotelMarkersJsonEl = document.getElementById("hotel-markers-json");
let dashboardHotels = [];
if (hotelMarkersJsonEl) {
    try {
        const parsedHotels = JSON.parse(hotelMarkersJsonEl.textContent || "[]");
        dashboardHotels = Array.isArray(parsedHotels) ? parsedHotels : [];
    } catch (_error) {
        dashboardHotels = [];
    }
}
let isChatBusy = false;
let distanceUpdateTimer = null;
const ROUTE_DEBOUNCE_MS = 120;
const MIN_ROUTE_QUERY_LENGTH = 2;
let googleMap = null;
let directionsService = null;
let directionsRenderer = null;
let activeMapRequestToken = 0;
let activeRouteUpdateSequence = 0;
let lastRouteQueryKey = "";
let lastRouteUpdateAt = 0;
let activeDistanceFetchController = null;
let activeChatFetchController = null;
const CHAT_REQUEST_TIMEOUT_MS = 12000;
let nearbyHotelMarkers = [];
let hotelInfoWindow = null;
let routeFallbackStartMarker = null;
let routeFallbackEndMarker = null;
let routeFallbackLine = null;
const DEFAULT_GOOGLE_EMBED_URL = "https://maps.google.com/maps?q=India&z=5&output=embed";

function setMapFallbackMessage(message, isError = false) {
    if (!mapFallbackEl) return;

    if (!message) {
        mapFallbackEl.textContent = "";
        mapFallbackEl.classList.add("hidden");
        mapFallbackEl.classList.remove("error");
        return;
    }

    mapFallbackEl.textContent = message;
    mapFallbackEl.classList.remove("hidden");
    mapFallbackEl.classList.toggle("error", isError);
}

function setMapDistanceBadge(distanceDisplay, duration = "", isError = false) {
    if (!mapDistancePillEl) return;

    const distance = String(distanceDisplay || "Distance unavailable").trim();
    const suffix = duration ? ` | Time: ${duration}` : "";
    mapDistancePillEl.textContent = `Distance: ${distance}${suffix}`;
    mapDistancePillEl.classList.toggle("error", Boolean(isError));
}

function setFallbackMapVisible(isVisible) {
    if (fallbackMapEl) {
        fallbackMapEl.classList.toggle("hidden", !isVisible);
    }
    if (googleMapEl) {
        googleMapEl.classList.toggle("map-disabled", isVisible);
    }
}

function initializeFallbackMap() {
    if (!fallbackMapEl) {
        return false;
    }

    setFallbackMapVisible(true);
    if (!fallbackMapEl.getAttribute("src")) {
        fallbackMapEl.setAttribute("src", DEFAULT_GOOGLE_EMBED_URL);
    }
    return true;
}

function setFallbackMapSource(url) {
    if (!fallbackMapEl || !url) return;
    if (fallbackMapEl.getAttribute("src") !== url) {
        fallbackMapEl.setAttribute("src", url);
    }
}

function buildGoogleEmbedUrl(params) {
    const url = new URL("https://maps.google.com/maps");
    Object.entries(params).forEach(([key, value]) => {
        const cleanValue = String(value || "").trim();
        if (cleanValue) {
            url.searchParams.set(key, cleanValue);
        }
    });
    url.searchParams.set("output", "embed");
    return url.toString();
}

function hasMeaningfulRouteLabel(label, placeholder) {
    const cleanLabel = String(label || "").trim();
    return Boolean(cleanLabel && cleanLabel.toLowerCase() !== String(placeholder || "").toLowerCase());
}

function renderFallbackRouteByLabels(startLabel = "Start", destinationLabel = "Destination") {
    if (!initializeFallbackMap()) {
        return false;
    }

    const hasStart = hasMeaningfulRouteLabel(startLabel, "Start");
    const hasDestination = hasMeaningfulRouteLabel(destinationLabel, "Destination");
    if (!hasStart || !hasDestination) {
        return false;
    }

    setFallbackMapSource(buildGoogleEmbedUrl({
        saddr: startLabel,
        daddr: destinationLabel,
        dirflg: "d",
    }));
    return true;
}

function routePointLabel(point, fallbackLabel, preferFallback = false) {
    const cleanFallback = String(fallbackLabel || "").trim();
    if (preferFallback && cleanFallback) {
        return cleanFallback;
    }

    const normalized = normalizeMapCoords(point);
    if (normalized) {
        return `${normalized.lat.toFixed(5)},${normalized.lng.toFixed(5)}`;
    }
    return cleanFallback;
}

function renderFallbackRoute(path, startLabel = "Start", destinationLabel = "Destination") {
    if (!initializeFallbackMap()) {
        return false;
    }

    const routePath = (Array.isArray(path) ? path : [])
        .map((point) => normalizeMapCoords(point))
        .filter(Boolean);

    if (routePath.length < 2) {
        return renderFallbackRouteByLabels(startLabel, destinationLabel);
    }

    setFallbackMapSource(buildGoogleEmbedUrl({
        saddr: routePointLabel(routePath[0], startLabel, true),
        daddr: routePointLabel(routePath[routePath.length - 1], destinationLabel, true),
        dirflg: "d",
    }));
    return true;
}

function updateFallbackMapView(startCoords, endCoords, startLabel = "Start", destinationLabel = "Destination") {
    if (!initializeFallbackMap()) return;

    const points = [normalizeMapCoords(startCoords), normalizeMapCoords(endCoords)].filter(Boolean);
    if (!points.length) {
        renderFallbackRouteByLabels(startLabel, destinationLabel);
        return;
    }

    if (points.length >= 2) {
        renderFallbackRoute(points, startLabel, destinationLabel);
        return;
    }

    setFallbackMapSource(buildGoogleEmbedUrl({
        q: routePointLabel(points[0], startLabel || destinationLabel || "India", true),
        z: "8",
    }));
}

function initializeGoogleMap() {
    if (!googleMapEl || !window.google || !window.google.maps) {
        return false;
    }

    setFallbackMapVisible(false);

    if (!googleMap) {
        googleMap = new window.google.maps.Map(googleMapEl, {
            center: { lat: 22.9734, lng: 78.6569 },
            zoom: 5,
            mapTypeId: window.google.maps.MapTypeId.ROADMAP,
            mapTypeControl: false,
            streetViewControl: false,
            fullscreenControl: true,
            styles: [],
        });
    }

    if (!directionsService) {
        directionsService = new window.google.maps.DirectionsService();
    }

    if (!directionsRenderer) {
        directionsRenderer = new window.google.maps.DirectionsRenderer({
            map: googleMap,
            suppressMarkers: true,
            polylineOptions: {
                strokeColor: "#1d63d0",
                strokeOpacity: 0.9,
                strokeWeight: 6,
            },
        });
    }

    return true;
}

function clearRouteFallbackGraphics() {
    [routeFallbackStartMarker, routeFallbackEndMarker, routeFallbackLine].forEach((item) => {
        if (item && typeof item.setMap === "function") {
            item.setMap(null);
        }
    });
    routeFallbackStartMarker = null;
    routeFallbackEndMarker = null;
    routeFallbackLine = null;
}

function renderRouteEndpointMarkers(startPosition, endPosition, startLabel = "Start", destinationLabel = "Destination") {
    if (!initializeGoogleMap() || !startPosition || !endPosition) {
        return;
    }

    routeFallbackStartMarker = new window.google.maps.Marker({
        map: googleMap,
        position: startPosition,
        title: String(startLabel || "Start").trim(),
        label: "A",
    });
    routeFallbackEndMarker = new window.google.maps.Marker({
        map: googleMap,
        position: endPosition,
        title: String(destinationLabel || "Destination").trim(),
        label: "B",
    });
}

function normalizeMapCoords(rawCoords) {
    const lat = Number(rawCoords?.lat);
    const lng = Number(rawCoords?.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
        return null;
    }
    if (lat < -90 || lat > 90 || lng < -180 || lng > 180) {
        return null;
    }
    return { lat, lng };
}

async function requestOsrmRoadRoute(startCoords, endCoords, startLabel = "Start", destinationLabel = "Destination") {
    const start = normalizeMapCoords(startCoords);
    const end = normalizeMapCoords(endCoords);
    if (!start || !end) {
        return { ok: false, reason: "coords-missing" };
    }

    try {
        const url = `https://router.project-osrm.org/route/v1/driving/${start.lng},${start.lat};${end.lng},${end.lat}?overview=full&geometries=geojson`;
        const response = await fetch(url);
        if (!response.ok) {
            return { ok: false, reason: `http-${response.status}` };
        }
        const payload = await response.json();
        const route = Array.isArray(payload?.routes) ? payload.routes[0] : null;
        const coordinates = route?.geometry?.coordinates;
        if (!route || !Array.isArray(coordinates) || coordinates.length < 2) {
            return { ok: false, reason: "osrm-no-route" };
        }

        const path = coordinates
            .map((point) => ({ lat: Number(point?.[1]), lng: Number(point?.[0]) }))
            .filter((point) => Number.isFinite(point.lat) && Number.isFinite(point.lng));

        if (path.length < 2) {
            return { ok: false, reason: "osrm-invalid-geometry" };
        }

        if (initializeGoogleMap()) {
            if (directionsRenderer) {
                directionsRenderer.set("directions", null);
            }
            clearRouteFallbackGraphics();

            routeFallbackStartMarker = new window.google.maps.Marker({
                map: googleMap,
                position: path[0],
                label: "A",
                title: startLabel,
            });
            routeFallbackEndMarker = new window.google.maps.Marker({
                map: googleMap,
                position: path[path.length - 1],
                label: "B",
                title: destinationLabel,
            });
            routeFallbackLine = new window.google.maps.Polyline({
                map: googleMap,
                path: path,
                geodesic: false,
                strokeColor: "#1a73e8",
                strokeOpacity: 0.95,
                strokeWeight: 6,
            });

            const bounds = new window.google.maps.LatLngBounds();
            path.forEach((point) => bounds.extend(point));
            googleMap.fitBounds(bounds);
        } else {
            renderFallbackRoute(path, startLabel, destinationLabel);
        }

        const distanceKm = Number(route.distance || 0) / 1000;
        const durationMin = Math.max(1, Math.round(Number(route.duration || 0) / 60));

        return {
            ok: true,
            route_name: `${startLabel} to ${destinationLabel}` ,
            distance_display: `${distanceKm.toFixed(1)} km`,
            duration: `${durationMin} mins`,
            source: "OSRM Road Route",
        };
    } catch (_error) {
        return { ok: false, reason: "osrm-request-failed" };
    }
}

function requestGoogleRouteWithCoordinates(startCoords, endCoords, startLabel = "Start", destinationLabel = "Destination") {
    return new Promise((resolve) => {
        if (!initializeGoogleMap()) {
            resolve({ ok: false, reason: "map-not-ready" });
            return;
        }
        const start = normalizeMapCoords(startCoords);
        const end = normalizeMapCoords(endCoords);
        if (!start || !end) {
            resolve({ ok: false, reason: "coords-missing" });
            return;
        }

        const requestToken = ++activeMapRequestToken;
        directionsService.route(
            {
                origin: start,
                destination: end,
                travelMode: window.google.maps.TravelMode.DRIVING,
                unitSystem: window.google.maps.UnitSystem.METRIC,
                provideRouteAlternatives: false,
            },
            (result, status) => {
                if (requestToken !== activeMapRequestToken) {
                    resolve({ ok: false, reason: "stale-request" });
                    return;
                }
                if (status === "OK" && result?.routes?.length) {
                    clearRouteFallbackGraphics();
                    directionsRenderer.setDirections(result);
                    const leg = result.routes[0]?.legs?.[0];
                    if (leg?.start_location && leg?.end_location) {
                        renderRouteEndpointMarkers(leg.start_location, leg.end_location, startLabel, destinationLabel);
                    }
                    resolve({
                        ok: true,
                        route_name: `${startLabel} to ${destinationLabel}`,
                        distance_display: leg?.distance?.text || "Distance unavailable",
                        duration: leg?.duration?.text || "",
                        source: "Google Maps Directions (coords)",
                    });
                    return;
                }
                resolve({ ok: false, reason: String(status || "route-error") });
            }
        );
    });
}


function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function clearNearbyHotelMarkers() {
    nearbyHotelMarkers.forEach((marker) => marker.setMap(null));
    nearbyHotelMarkers = [];
}

function renderNearbyHotelMarkers(hotels) {
    if (!initializeGoogleMap() || !Array.isArray(hotels)) {
        return;
    }

    clearNearbyHotelMarkers();
    if (!hotelInfoWindow) {
        hotelInfoWindow = new window.google.maps.InfoWindow();
    }

    hotels.forEach((hotel) => {
        const lat = Number(hotel?.lat);
        const lng = Number(hotel?.lng);
        if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
            return;
        }

        const marker = new window.google.maps.Marker({
            map: googleMap,
            position: { lat, lng },
            title: String(hotel?.name || "Nearby Hotel"),
            icon: {
                path: window.google.maps.SymbolPath.BACKWARD_CLOSED_ARROW,
                scale: 5,
                fillColor: "#1c7a53",
                fillOpacity: 0.95,
                strokeColor: "#ffffff",
                strokeWeight: 1,
            },
        });

        marker.addListener("click", () => {
            const detailsHtml = `
                <div style="min-width:220px;max-width:260px;font-size:12px;line-height:1.35;">
                    <strong style="font-size:13px;">${escapeHtml(hotel?.name || "Nearby Hotel")}</strong><br>
                    Price: Rs ${escapeHtml(hotel?.price || "N/A")} / night<br>
                    Rating: ${escapeHtml(hotel?.rating || "N/A")}/5<br>
                    Phone: ${escapeHtml(hotel?.phone || "Not publicly listed")}<br>
                    ${escapeHtml(hotel?.address || "")}
                </div>
            `;
            hotelInfoWindow.setContent(detailsHtml);
            hotelInfoWindow.open({ map: googleMap, anchor: marker });
        });

        nearbyHotelMarkers.push(marker);
    });
}




window.initGoogleMap = function initGoogleMap() {
    if (!initializeGoogleMap()) {
        setMapFallbackMessage("Google Map could not initialize.", true);
        setFallbackMapVisible(true);
        return;
    }
    renderNearbyHotelMarkers(dashboardHotels);
    setMapFallbackMessage("");
    queueDistanceUpdate();
};

window.initFallbackMap = function initFallbackMap() {
    if (initializeFallbackMap()) {
        setMapFallbackMessage("");
    } else {
        setMapFallbackMessage("Map library could not load. Check your internet connection.", true);
    }
    queueDistanceUpdate(true);
};

window.handleGoogleMapsLoadError = function handleGoogleMapsLoadError(message) {
    const fallbackMessage = message || "Google Map failed to load. Check API key and billing setup.";
    setFallbackMapVisible(true);
    setMapFallbackMessage(fallbackMessage, true);
    setMapDistanceBadge(routeDistanceEl?.textContent || "Distance unavailable", "", true);
    setOutputMessage(fallbackMessage);
};

window.gm_authFailure = function gmAuthFailure() {
    window.handleGoogleMapsLoadError("Google Maps authorization failed. Showing fallback map.");
};

function requestGoogleRoute(startingPoint, destination) {
    return new Promise((resolve) => {
        if (!googleMapEl) {
            resolve({ ok: false, reason: "map-not-present" });
            return;
        }

        if (!initializeGoogleMap()) {
            setMapFallbackMessage("Loading Google Map...");
            resolve({ ok: false, reason: "map-not-ready" });
            return;
        }

        const requestToken = ++activeMapRequestToken;
        directionsService.route(
            {
                origin: startingPoint,
                destination: destination,
                travelMode: window.google.maps.TravelMode.DRIVING,
                unitSystem: window.google.maps.UnitSystem.METRIC,
                provideRouteAlternatives: false,
            },
            (result, status) => {
                if (requestToken !== activeMapRequestToken) {
                    resolve({ ok: false, reason: "stale-request" });
                    return;
                }

                if (status === "OK" && result?.routes?.length) {
                    clearRouteFallbackGraphics();
                    directionsRenderer.setDirections(result);
                    setMapFallbackMessage("");

                    const leg = result.routes[0]?.legs?.[0];
                    if (leg?.start_location && leg?.end_location) {
                        renderRouteEndpointMarkers(leg.start_location, leg.end_location, startingPoint, destination);
                    }
                    const routeName = `${startingPoint} to ${destination}`;
                    const distanceDisplay = leg?.distance?.text || "Distance unavailable";
                    const duration = leg?.duration?.text || "";

                    resolve({
                        ok: true,
                        route_name: routeName,
                        distance_display: distanceDisplay,
                        duration: duration,
                        source: "Google Maps Directions",
                    });
                    return;
                }

                directionsRenderer.set("directions", null);
                setMapFallbackMessage("Route is not available on Google Maps for this pair.", true);
                resolve({ ok: false, reason: String(status || "route-error") });
            }
        );
    });
}

function updateSplitValues() {
    const total = Number(totalExpenseEl?.dataset.total || 0);
    const people = Number(peopleSelect?.value || 1);
    const perPerson = Math.floor(total / Math.max(people, 1));

    if (peopleCountEl) peopleCountEl.textContent = String(people);
    if (perPersonEl) perPersonEl.textContent = `Rs ${perPerson}`;
}

function appendMessage(type, text) {
    if (!chatWindow || !text.trim()) return;

    const message = document.createElement("div");
    message.className = `message ${type}`;
    message.textContent = text;
    chatWindow.appendChild(message);
    chatWindow.scrollTop = chatWindow.scrollHeight;
}

function setOutputMessage(text) {
    if (actionOutput && text) {
        actionOutput.textContent = text;
    }
}

function hasRouteSurface() {
    return Boolean(routeNameEl || routeDistanceEl || googleMapEl);
}

function hasSufficientRouteInput(startingPoint, destination) {
    return (
        startingPoint.length >= MIN_ROUTE_QUERY_LENGTH &&
        destination.length >= MIN_ROUTE_QUERY_LENGTH
    );
}

function normalizeRouteKey(startingPoint, destination) {
    const normalize = (value) => String(value || "").trim().toLowerCase().replace(/\s+/g, " ");
    return `${normalize(startingPoint)}=>${normalize(destination)}`;
}



function applyRouteDisplay(routeName, distanceDisplay, source, duration = "") {
    if (routeNameEl) routeNameEl.textContent = routeName || "Route unavailable";
    if (routeDistanceEl) {
        routeDistanceEl.textContent = duration
            ? `${distanceDisplay || "Distance unavailable"} (${duration})`
            : (distanceDisplay || "Distance unavailable");
    }
    if (distanceSourceEl) distanceSourceEl.textContent = `Source: ${source || "unknown"}`;
    setMapDistanceBadge(distanceDisplay, duration);
}

function markRouteUpdate(routeKey) {
    lastRouteQueryKey = routeKey;
    lastRouteUpdateAt = Date.now();
}

function abortActiveDistanceFetch() {
    if (!activeDistanceFetchController) return;
    activeDistanceFetchController.abort();
    activeDistanceFetchController = null;
}

function collectTripContext() {
    return {
        starting_point: (startingPointInput?.value || "").trim(),
        destination: (destinationInput?.value || "").trim(),
        visited_place: (destinationInput?.value || "").trim(),
        people: Number(peopleSelect?.value || 4),
        budget: Number(budgetSelect?.value || 20000),
        total_expense: Number(totalExpenseEl?.dataset.total || 0)
    };
}

function setChatBusy(state) {
    isChatBusy = state;
    if (sendBtn) {
        sendBtn.disabled = state;
        sendBtn.textContent = state ? "Thinking..." : "Send";
    }
}

async function sendUserMessage(text) {
    const cleanText = text.trim();
    if (!cleanText || isChatBusy) return;

    appendMessage("user", cleanText);
    setChatBusy(true);

    if (activeChatFetchController) {
        activeChatFetchController.abort();
    }
    activeChatFetchController = new AbortController();
    const timeoutId = window.setTimeout(() => {
        if (activeChatFetchController) {
            activeChatFetchController.abort();
        }
    }, CHAT_REQUEST_TIMEOUT_MS);

    try {
        const response = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            signal: activeChatFetchController.signal,
            body: JSON.stringify({
                message: cleanText,
                context: collectTripContext()
            })
        });

        const payload = await response.json();
        if (!response.ok) {
            appendMessage("bot", payload.reply || "Unable to process this message right now.");
            if (response.status === 401) {
                window.location.href = "/login";
            }
            return;
        }
        appendMessage("bot", payload.reply || "I did not generate a reply. Please try again.");
        setOutputMessage("AI Chatbot returned a response with destination context.");
    } catch (error) {
        if (error?.name === "AbortError") {
            appendMessage("bot", "Response timed out. I switched to local travel assistance. Ask itinerary, hotels, spots, food, activities, budget, or route.");
        } else {
            appendMessage("bot", "Server connection failed. Please check if Flask app is running.");
        }
    } finally {
        window.clearTimeout(timeoutId);
        activeChatFetchController = null;
        setChatBusy(false);
    }
}

async function updateRouteDistance() {
    if (!hasRouteSurface()) return;

    const startingPoint = (startingPointInput?.value || "").trim();
    const destination = (destinationInput?.value || "").trim();
    if (!hasSufficientRouteInput(startingPoint, destination)) return;

    const routeKey = normalizeRouteKey(startingPoint, destination);
    if (routeKey === lastRouteQueryKey && Date.now() - lastRouteUpdateAt < 450) {
        return;
    }

    const requestSequence = ++activeRouteUpdateSequence;

    if (startPlaceEl) startPlaceEl.textContent = `From: ${startingPoint}`;
    if (destinationPlaceEl) destinationPlaceEl.textContent = `To: ${destination}`;

    const googleRoute = await requestGoogleRoute(startingPoint, destination);
    if (requestSequence !== activeRouteUpdateSequence) {
        return;
    }

    if (googleRoute.ok) {
        applyRouteDisplay(
            googleRoute.route_name || `${startingPoint} to ${destination}`,
            googleRoute.distance_display,
            googleRoute.source,
            googleRoute.duration || ""
        );
        setOutputMessage(`Distance ready: ${googleRoute.route_name} is ${googleRoute.distance_display}.`);
        markRouteUpdate(routeKey);
        return;
    }

    renderFallbackRouteByLabels(startingPoint, destination);

    try {
        abortActiveDistanceFetch();
        activeDistanceFetchController = new AbortController();

        const response = await fetch("/api/distance", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            signal: activeDistanceFetchController.signal,
            body: JSON.stringify({
                starting_point: startingPoint,
                destination: destination,
            }),
        });
        const payload = await response.json();

        if (requestSequence !== activeRouteUpdateSequence) {
            return;
        }

        if (response.status === 401) {
            window.location.href = "/login";
            return;
        }

        const startCoords = normalizeMapCoords(payload.start_coords);
        const destinationCoords = normalizeMapCoords(payload.destination_coords);
        updateFallbackMapView(startCoords, destinationCoords, startingPoint, destination);

        const coordinateRoute = await requestGoogleRouteWithCoordinates(
            startCoords,
            destinationCoords,
            payload.start_name || startingPoint,
            payload.destination_name || destination
        );

        if (requestSequence !== activeRouteUpdateSequence) {
            return;
        }

        if (coordinateRoute.ok) {
            applyRouteDisplay(
                coordinateRoute.route_name,
                coordinateRoute.distance_display || payload.distance_display || "Distance unavailable",
                coordinateRoute.source || "Google Maps Directions",
                coordinateRoute.duration || ""
            );
            setMapFallbackMessage("");
            setOutputMessage(`Distance ready: ${coordinateRoute.route_name} is ${coordinateRoute.distance_display}.`);
            markRouteUpdate(routeKey);
            return;
        }

        const osrmRoute = await requestOsrmRoadRoute(
            startCoords,
            destinationCoords,
            payload.start_name || startingPoint,
            payload.destination_name || destination
        );

        if (requestSequence !== activeRouteUpdateSequence) {
            return;
        }

        if (osrmRoute.ok) {
            applyRouteDisplay(
                osrmRoute.route_name,
                osrmRoute.distance_display || payload.distance_display || "Distance unavailable",
                osrmRoute.source || "OSRM Road Route",
                osrmRoute.duration || ""
            );
            setMapFallbackMessage("Road route loaded via OSRM.");
            setOutputMessage(`Distance ready: ${osrmRoute.route_name} is ${osrmRoute.distance_display}.`);
            markRouteUpdate(routeKey);
            return;
        }

        applyRouteDisplay(
            payload.route_name || `${startingPoint} to ${destination}` ,
            payload.distance_display || "Distance unavailable",
            payload.source || "unknown"
        );

        const approximateRouteVisible = renderFallbackRoute(
            [startCoords, destinationCoords],
            payload.start_name || startingPoint,
            payload.destination_name || destination
        );

        setMapFallbackMessage(
            approximateRouteVisible
                ? "Approximate route line shown."
                : "Road-by-road route is unavailable for this pair.",
            !approximateRouteVisible
        );

        if (response.status >= 400) {
            setOutputMessage(payload.message || payload.distance_display || "Distance could not be fetched.");
        } else {
            setOutputMessage(`Distance ready: ${payload.route_name} is ${payload.distance_display}.`);
        }
    } catch (error) {
        if (error?.name === "AbortError") {
            return;
        }
        if (routeDistanceEl) routeDistanceEl.textContent = "Distance unavailable";
        if (distanceSourceEl) distanceSourceEl.textContent = "Source: request-failed";
        setMapDistanceBadge("Distance unavailable", "", true);
        setMapFallbackMessage(
            "Road route could not be loaded. Check map key, billing, internet, and destination spelling.",
            true
        );
    } finally {
        if (requestSequence === activeRouteUpdateSequence) {
            activeDistanceFetchController = null;
        }
    }

    markRouteUpdate(routeKey);
}
function queueDistanceUpdate(immediate = false) {
    if (!hasRouteSurface()) return;

    const startingPoint = (startingPointInput?.value || "").trim();
    const destination = (destinationInput?.value || "").trim();
    if (!hasSufficientRouteInput(startingPoint, destination)) return;

    if (distanceUpdateTimer) {
        clearTimeout(distanceUpdateTimer);
    }

    const delay = immediate ? 0 : ROUTE_DEBOUNCE_MS;
    distanceUpdateTimer = setTimeout(() => {
        updateRouteDistance();
    }, delay);
}

if (peopleSelect) {
    peopleSelect.addEventListener("change", updateSplitValues);
}

if (startingPointInput) {
    startingPointInput.addEventListener("input", () => queueDistanceUpdate());
    startingPointInput.addEventListener("change", () => queueDistanceUpdate(true));
    startingPointInput.addEventListener("blur", () => queueDistanceUpdate(true));
}

if (destinationInput) {
    destinationInput.addEventListener("input", () => queueDistanceUpdate());
    destinationInput.addEventListener("change", () => {
        queueDistanceUpdate(true);
        const newDestination = (destinationInput.value || "").trim();
        if (newDestination) {
            setOutputMessage(`Chatbot destination updated: ${newDestination}`);
        }
    });
    destinationInput.addEventListener("blur", () => queueDistanceUpdate(true));
}

if (splitBtn) {
    splitBtn.addEventListener("click", updateSplitValues);
    splitBtn.addEventListener("click", () => {
        setOutputMessage(`Expense split complete. Each person pays ${perPersonEl?.textContent || "calculated value"}.`);
    });
}

replyButtons.forEach((button) => {
    button.addEventListener("click", async () => {
        await sendUserMessage(button.dataset.reply || "");
    });
});

if (sendBtn) {
    sendBtn.addEventListener("click", async () => {
        await sendUserMessage(chatText?.value || "");
        if (chatText) chatText.value = "";
    });
}

if (chatText) {
    chatText.addEventListener("keydown", async (event) => {
        if (event.key === "Enter") {
            event.preventDefault();
            await sendUserMessage(chatText.value || "");
            chatText.value = "";
        }
    });
}

if (tripForm) {
    tripForm.addEventListener("submit", () => {
        const destination = destinationInput?.value || "selected destination";
        const people = peopleSelect?.value || "group";
        setOutputMessage(`Generating itinerary for ${destination} with ${people} travelers...`);
    });
}

hotelSelectButtons.forEach((button) => {
    button.addEventListener("click", () => {
        const hotelName = button.getAttribute("data-hotel") || "Selected hotel";
        const hotelPrice = button.getAttribute("data-price") || "0";
        setOutputMessage(`Hotel selected: ${hotelName} at Rs ${hotelPrice} per night.`);
    });
});

menuLinks.forEach((link) => {
    link.addEventListener("click", (event) => {
        event.preventDefault();
        const targetId = link.getAttribute("href");
        if (!targetId) return;

        const section = document.querySelector(targetId);
        if (section) {
            section.scrollIntoView({ behavior: "smooth", block: "start" });
        }

        menuLinks.forEach((menuLink) => menuLink.classList.remove("active"));
        link.classList.add("active");
        setOutputMessage(link.getAttribute("data-output") || "Section opened.");
    });
});

if (menuLinks.length > 0) {
    menuLinks[0].classList.add("active");
}

setMapDistanceBadge(routeDistanceEl?.textContent || "Distance unavailable");
queueDistanceUpdate();
