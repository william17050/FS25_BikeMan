-- BikeMan v0.3: links FS25 to an external smart-bike bridge using small files under modSettings/FS25_BikeMan/.
--   out.txt (game -> bridge, ~10 Hz): seq,speed_kmh,pitch_pct,terrain_pct,inVehicle,vehicleXml,cruiseState,cruiseKmh,engaged
--   in.xml  (bridge -> game):         <in seq="N" kph="25.0" rpm="70" watts="120"/>
-- While in.xml keeps changing (fresh) the vehicle's speed is held to `kph` via cruise control; kph <= 1 brakes to a stop.
-- If in.xml goes stale (bridge not running) the mod lets go and the game drives normally.
BikeMan = {}
BikeMan.INTERVAL = 100   -- ms between file exchanges
BikeMan.STALE = 2000     -- ms without a new seq before we let go
BikeMan.timer = 0
BikeMan.seq = 0
BikeMan.inSeq = nil
BikeMan.inAge = 1e9
BikeMan.target = nil     -- km/h, nil = not controlling
BikeMan.engaged = false
BikeMan.reported = {}
BikeMan.odoResets = 0    -- counts presses of the trip-reset key; the link zeroes its trip distance whenever this changes
BikeMan.resetKeyDown = false
BikeMan.resetFlash = 0   -- ms left to show "TRIP RESET" on the panel

local function log(msg) print("[BikeMan] " .. tostring(msg)) end
local function once(key, msg) if not BikeMan.reported[key] then BikeMan.reported[key] = true; log(msg) end end

function BikeMan:loadMap()
    self.dir = getUserProfileAppPath() .. "modSettings/FS25_BikeMan/"
    createFolder(self.dir)
    log("v0.3 loaded, folder = " .. self.dir)
end

function BikeMan:getVehicle()
    local v = nil
    if g_localPlayer ~= nil and g_localPlayer.getCurrentVehicle ~= nil then v = g_localPlayer:getCurrentVehicle() end
    if v == nil and g_currentMission ~= nil then v = g_currentMission.controlledVehicle end
    return v
end

-- pitch of the vehicle body as a grade in percent (+ = uphill); terrain slope 2 m ahead vs behind (misleading on bridges)
function BikeMan:measure(v)
    local fx, fy, fz = localDirectionToWorld(v.rootNode, 0, 0, 1)
    local horiz = math.sqrt(fx * fx + fz * fz)
    local pitchPct = horiz > 0.01 and (fy / horiz) * 100 or 0
    local terrain = 0
    if g_terrainNode ~= nil and horiz > 0.01 then
        local x, _, z = getWorldTranslation(v.rootNode)
        local ux, uz = fx / horiz, fz / horiz
        local hF = getTerrainHeightAtWorldPos(g_terrainNode, x + ux * 2, 0, z + uz * 2)
        local hB = getTerrainHeightAtWorldPos(g_terrainNode, x - ux * 2, 0, z - uz * 2)
        terrain = (hF - hB) / 4 * 100
    end
    return pitchPct, terrain
end

function BikeMan:readIn()
    local path = self.dir .. "in.xml"
    if not fileExists(path) then return end
    local id = loadXMLFile("bikeIn", path)
    if id == nil or id == 0 then return end
    local seq = getXMLInt(id, "in#seq")
    local kph = getXMLFloat(id, "in#kph")
    local rpm = getXMLFloat(id, "in#rpm")
    local watts = getXMLFloat(id, "in#watts")
    local grade = getXMLFloat(id, "in#grade")
    local kj = getXMLFloat(id, "in#kj")
    local scale = getXMLFloat(id, "in#hud")
    local brake = getXMLFloat(id, "in#brake")
    local units = getXMLString(id, "in#units")
    local dist = getXMLFloat(id, "in#dist")
    delete(id)
    if seq ~= nil and seq ~= self.inSeq then
        self.inSeq = seq
        self.inAge = 0
        self.target = kph or 0
        self.coastBrake = brake or 0
        self.hud = {rpm = rpm or 0, watts = watts or 0, grade = grade or 0, kj = kj or 0, scale = scale or 1.0, units = units or "both", dist = dist or 0}
    end
end

-- Hold the vehicle to self.target km/h with cruise control. Target <= 1 km/h: brake only while still rolling forward
-- (FS drives backwards when brake is pressed at a standstill), and let go completely once stopped.
-- Behaviour while the bridge is live:
--   pedalling (target > 1 km/h): cruise control holds the bike's speed.
--   not pedalling: freewheel (no cruise, no brake). When speed reaches ~0 (slowed or braked) the handbrake LATCHES and stays on
--   until you pedal again or press throttle. After a throttle release it will not re-latch until you have moved > 1.5 km/h.
-- The game passes doHandbrake into updateVehiclePhysics(axisForward, axisSide, doHandbrake, dt); we wrap the instance method once.
BikeMan.holdVehicle = nil
BikeMan.latched = false
BikeMan.armed = true
-- The bike's own brake force can be too weak to beat gravity on a downhill, so while latched also pin the bodies in place.
function BikeMan:freeze(v)
    pcall(function()
        for _, comp in ipairs(v.components or {}) do
            setLinearVelocity(comp.node, 0, 0, 0)
            setAngularVelocity(comp.node, 0, 0, 0)
        end
    end)
end

function BikeMan:hasImplement(v)          -- true when something (plow, trailer...) is attached
    local ok, list = pcall(function() return v:getAttachedImplements() end)
    return ok and type(list) == "table" and #list > 0
end

function BikeMan:wrap(v)
    if v.bikeManWrapped then return end
    v.bikeManWrapped = true
    local orig = v.updateVehiclePhysics
    v.updateVehiclePhysics = function(self, axisForward, axisSide, doHandbrake, dt)
        if type(doHandbrake) ~= "boolean" then
            once("sig", "updateVehiclePhysics unexpected signature, handbrake unavailable")
        elseif not BikeMan.latched and BikeMan.armed and BikeMan.target ~= nil and BikeMan.target <= 1.0
               and (axisForward or 0) < -0.1 and (self.lastSpeedReal or 0) * 3600 < 8 and (self.movingDirection or 0) >= 0 then
            BikeMan.latched, BikeMan.holdVehicle = true, self       -- braking at low speed: latch before FS reverses us
            log(string.format("handbrake latched (brake at low speed) speed=%.2f", (self.lastSpeedReal or 0) * 3600))
            BikeMan:freeze(self)
            return orig(self, 0, axisSide, true, dt)
        elseif BikeMan.holdVehicle == self then
            if (axisForward or 0) > 0.2 then      -- throttle pressed: release the latch
                BikeMan.latched, BikeMan.armed, BikeMan.holdVehicle = false, false, nil
                BikeMan.revT = 0
                log("handbrake released by throttle")
            elseif (axisForward or 0) < -0.2 and ((self.lastSpeedReal or 0) * 3600) < 1.0 then
                BikeMan.revT = (BikeMan.revT or 0) + (dt or 0)
                if BikeMan.revT > 500 then       -- reverse/brake held 0.5 s while stopped: let the player back up (hitching etc.)
                    BikeMan.latched, BikeMan.armed, BikeMan.holdVehicle = false, false, nil
                    BikeMan.revT = 0
                    log("handbrake released for reverse")
                else
                    BikeMan:freeze(self)
                    return orig(self, 0, axisSide, true, dt)
                end
            else
                BikeMan.revT = 0
                once("handbrake", "handbrake forced (signature ok)")
                BikeMan:freeze(self)
                return orig(self, 0, axisSide, true, dt)
            end
        elseif BikeMan.target ~= nil and BikeMan.target <= 1.0 and (BikeMan.coastBrake or 0) > 0 and not BikeMan.latched
               and (self.movingDirection or 0) >= 0 and (self.lastSpeedReal or 0) * 3600 > 1.0 and (axisForward or 0) <= 0.05
               and BikeMan:hasImplement(self) then
            -- not pedalling, rolling forward with an implement attached: gentle service brake (0 on downhills, so you can still freewheel them)
            return orig(self, -BikeMan.coastBrake, axisSide, doHandbrake, dt)
        end
        return orig(self, axisForward, axisSide, doHandbrake, dt)
    end
end

function BikeMan:release(v, why)
    if self.engaged then
        self.engaged = false
        pcall(function() v:setCruiseControlState(Drivable.CRUISECONTROL_STATE_OFF) end)
        log("cruise released: " .. why)
    end
end

function BikeMan:apply(v)
    if self.target == nil then
        self.latched, self.armed, self.holdVehicle = false, true, nil
        self:release(v, "bridge gone/stale")
        return
    end
    local ok, err = pcall(function()
        local speed = v.getLastSpeed ~= nil and v:getLastSpeed() or 0
        if speed > 1.5 then self.armed = true end
        if self.target > 1.0 then
            if self.latched then self.latched = false; log("handbrake released by pedalling") end
            self.holdVehicle = nil
            if not self.engaged then self.engaged = true; log("engaged by bridge") end
            v:setCruiseControlMaxSpeed(self.target, self.target)
            if v:getCruiseControlState() ~= Drivable.CRUISECONTROL_STATE_ACTIVE then
                v:setCruiseControlState(Drivable.CRUISECONTROL_STATE_ACTIVE)
            end
        else
            self:release(v, "freewheel")
            self:wrap(v)
            if not self.latched and self.armed and speed < 1.0 then
                self.latched = true
                log(string.format("handbrake latched (stopped) speed=%.2f", speed))
            end
            if self.latched then self.holdVehicle = v else self.holdVehicle = nil end
        end
    end)
    if not ok then once("apply", "APPLY ERROR (once): " .. tostring(err)) end
end

function BikeMan:writeOut(v)
    local speed, pitch, terrain, inVeh = 0, 0, 0, 0
    local name, cState, cKmh = "-", -1, 0
    if v ~= nil then
        inVeh = 1
        speed = v.getLastSpeed ~= nil and v:getLastSpeed() or 0
        self.lastSpeed = speed
        pitch, terrain = self:measure(v)
        name = tostring(v.configFileName):match("[^/]+$") or "?"
        pcall(function() cState = v:getCruiseControlState(); cKmh = v:getCruiseControlSpeed() end)
    end
    local f = io.open(self.dir .. "out.txt", "w")
    if f == nil then once("open", "cannot open out.txt"); return end
    f:write(string.format("%d,%.2f,%.2f,%.1f,%d,%s,%d,%.1f,%d,%d\n", self.seq, speed, pitch, terrain, inVeh, name, cState, cKmh, self.engaged and 1 or 0, self.odoResets))
    f:close()
end

-- Trip reset: Left Ctrl + Left Shift + O (checked every frame, fires once per press).
function BikeMan:checkResetKey(dt)
    if self.resetFlash > 0 then self.resetFlash = self.resetFlash - dt end
    if Input == nil or Input.isKeyPressed == nil or Input.KEY_lctrl == nil or Input.KEY_lshift == nil or Input.KEY_o == nil then
        once("nokey", "trip reset key not available in this game version")
        return
    end
    local down = Input.isKeyPressed(Input.KEY_lctrl) and Input.isKeyPressed(Input.KEY_lshift) and Input.isKeyPressed(Input.KEY_o)
    if down and not self.resetKeyDown then
        self.odoResets = self.odoResets + 1
        self.resetFlash = 2000
        log("trip reset requested (" .. self.odoResets .. ")")
    end
    self.resetKeyDown = down
end

function BikeMan:update(dt)
    if self.dir == nil then return end
    pcall(function() self:checkResetKey(dt) end)
    self.inAge = self.inAge + dt
    if self.inAge > self.STALE then self.target = nil end
    local v = self:getVehicle()
    if v ~= nil then self:apply(v) end           -- every frame, so a brake request is not lost
    self.timer = self.timer + dt
    if self.timer < self.INTERVAL then return end
    self.timer = 0
    self.seq = self.seq + 1
    local ok, err = pcall(function() self:writeOut(v); self:readIn() end)
    if not ok then once("io", "IO ERROR (once): " .. tostring(err)) end
end


-- HUD panel above the speedometer (only while the bridge is live). Sized from the speedometer's own overlay so it scales with UI size.
BikeMan.modDir = g_currentModDirectory
BikeMan.hudFailed = false
BikeMan.overlays = {}
function BikeMan:getOverlay(name)             -- lazy-load images/<name>.dds (PNG fallback); false = unavailable
    local o = self.overlays[name]
    if o ~= nil then return o end
    for _, ext in ipairs({".dds", ".png"}) do
        local ov = createImageOverlay(self.modDir .. "images/" .. name .. ext)
        if ov ~= nil and ov ~= 0 then self.overlays[name] = ov; return ov end
    end
    self.overlays[name] = false
    log("image not loaded: " .. name .. " (using plain rectangle)")
    return false
end
function BikeMan:drawHud(sm)
    if self.hudFailed or self.target == nil or self.hud == nil or sm.vehicle == nil then return end
    local ok, err = pcall(function()
        local posX = sm:getPosition()
        local bg = sm.speedBg
        local function dim(o, getter, field)
            if type(o[getter]) == "function" then return o[getter](o) end
            if o[field] ~= nil then return o[field] end
            if o.overlay ~= nil and o.overlay[field] ~= nil then return o.overlay[field] end
            return nil
        end
        local bw, bh = dim(bg, "getWidth", "width"), dim(bg, "getHeight", "height")
        if bw == nil or bh == nil then
            local keys = {}
            for k in pairs(bg) do keys[#keys + 1] = tostring(k) end
            error("speedBg has no width/height; fields: " .. table.concat(keys, ","))
        end
        local uw, uh = bw / 232, bh / 232              -- one design pixel in screen width / height
        local h = self.hud
        local k = h.scale or 1.0                       -- user size multiplier (--hud-scale in fs25_link.py)
        local right = posX - 6 * uw
        local bottom = bg.y + bh + 6 * uh
        local pw, ph = 340 * k * uw, 150 * k * uh
        local left = right - pw
        local bgImg = self:getOverlay("hud_bg")
        if bgImg then renderOverlay(bgImg, left, bottom, pw, ph) else drawFilledRect(left, bottom, pw, ph, 0, 0, 0, 0.6) end
        local icon = self:getOverlay("hud_icon")
        if icon then renderOverlay(icon, left + 12 * k * uw, bottom + 118 * k * uh, 28 * k * uw, 28 * k * uh) end
        local state = self.latched and "HELD" or (self.target > 1.0 and "PEDALLING" or "COASTING")
        local function txt(x, y, size, s)
            renderText(left + x * k * uw, bottom + y * k * uh, size * k * uh, s)
        end
        setTextAlignment(RenderText.ALIGN_LEFT)
        setTextBold(true)
        setTextColor(0.47, 0.84, 1, 1)
        txt(48, 123, 22, "BIKEMAN")
        setTextColor(1, 1, 1, 1)
        local km = h.dist or 0
        local mi = km * 0.621371
        local distTxt
        if self.resetFlash > 0 then distTxt = "TRIP RESET"
        elseif h.units == "mph" then distTxt = string.format("%.2f mi", mi)
        elseif h.units == "kmh" then distTxt = string.format("%.2f km", km)
        else distTxt = string.format("%.2f mi  %.2f km", mi, km) end
        setTextAlignment(RenderText.ALIGN_RIGHT)
        txt(332, 123, 20, distTxt)
        setTextAlignment(RenderText.ALIGN_LEFT)
        setTextColor(1, 1, 1, 1)
        txt(10, 74, 46, string.format("%d W", h.watts))
        txt(190, 78, 32, string.format("%d rpm", h.rpm))
        setTextColor(0.6, 0.9, 1, 1)
        txt(10, 42, 26, state)
        setTextColor(1, 1, 1, 1)
        txt(190, 42, 26, string.format("%+.1f%%", h.grade))
        setTextBold(false)
        setTextColor(0.9, 0.9, 0.9, 1)
        local kmh = self.lastSpeed or 0
        local mph = kmh * 0.621371
        local speedTxt
        if h.units == "mph" then speedTxt = string.format("%.1f mph", mph)
        elseif h.units == "kmh" then speedTxt = string.format("%.1f km/h", kmh)
        else speedTxt = string.format("%.0f mph (%.0f km/h)", mph, kmh) end
        txt(10, 10, 24, string.format("%s   %.1f kJ", speedTxt, h.kj))
        setTextColor(1, 1, 1, 1)
    end)
    if not ok then self.hudFailed = true; log("HUD ERROR (disabled): " .. tostring(err)) end
end

if SpeedMeterDisplay ~= nil then
    SpeedMeterDisplay.draw = Utils.appendedFunction(SpeedMeterDisplay.draw, function(self) BikeMan:drawHud(self) end)
else
    log("SpeedMeterDisplay not found, no HUD")
end

addModEventListener(BikeMan)
