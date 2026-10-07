// tramdo - a tram distribution office: the game's road distribution office, for cargo trams.
//
// Trams are rail vehicles to the engine (VEHICLETYPE_RAIL_LOCOMOTIVE / _RAIL_VAGON in the "tram"
// train group) but use road infrastructure: the tram depot is a road depot with $SUBTYPE_TRAM, tram
// stations are road-style stations. Our offices are the road distribution office
// ($TYPE_DISTRIBUTION_OFFICE, building type 0x2B) with $SUBTYPE_TRAM on a tram-depot layout, which
// plans and dispatches trams natively once two things are fixed.
//
// Which vehicles. SOVIET64 0x3E2900(game, building, vehicle type, flag, x) - "may this vehicle type
// use this building" - is asked by the purchase list, vehicle assignment and production-line
// delivery, and a road office never takes a rail vehicle. The tram depot instead admits vehicles
// whose train-group list (vehicle +0x96B8, std::vector<int>) holds the "tram" group (id from
// 0x25C7B0(game, "tram")). This plugin answers that question for our offices only - buildings whose
// object name starts with object_prefix (tramdo.ini): any cargo vehicle of the tram group may
// (passenger trams - cargo class PASSANGER, which every base-game tram is - may not), nothing else
// may; an office with a limit_<object> line takes only tram sets up to that length, measured by the
// game's own 0x25C270(vehicle type) (the vehicle's +0x7A78 plus each $TRAINSET wagon's, the sum the
// train office checks against its max train length). Every other building gets the game's (and
// other plugins') answer.
//
// Research. A road distribution office unlocks with the "distribution_office" research (it unlocks
// building type 0x2B). For our offices the plugin adds the research named by `research` (default
// railway_distribution_office, which itself needs distribution_office): 0x2F76C0(game, building
// descriptor) fills game +0x11790 (std::vector of research records) with the researches still
// blocking a building - the build menu treats a non-empty list as locked and names them. After the
// game's own pass the plugin appends that research's record while it is unfinished.
//
// Fuel. The road office's update (0x1C6050, building type 0x2B) walks its parked vehicles and, when
// the game runs with fuel (game +0x5B0 == 2), treats a vehicle whose fuel (vehicle +0x5F0) is <= 0 as
// empty: it tries to refuel it from the office's own fuel storage and skips it. Electric vehicles
// (vehicle type +0x8680 byte set) have no fuel level - +0x5F0 stays 0 - and the base game never puts
// one in an office, so a tram was "empty" forever and never dispatched. For our offices the plugin
// runs that update with the fuel mode off and restores it straight after.

#include "../../../vendor/TesmioLoader/src/tesmio_api.h"

#include <windows.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <stdlib.h>

static const TsmHost* H;

#define RVA_CAN_USE     0x3E2900
#define RVA_GROUP_ID    0x25C7B0
#define RVA_SET_LENGTH  0x25C270        // float (vehicle type): its length plus its $TRAINSET wagons'
#define RVA_GAME        0x9D4F10
#define BLD_TYPEDESC    0x318
#define TD_TYPE         0x360
#define VT_IDENT        0x200
#define VT_GROUPS       0x96B8          // std::vector<int> of train-group ids: begin, end
#define VT_CARGO        0x8600          // RESOURCE_TRANSPORT_* class: COVERED 0 .. PASSANGER 7 .. WASTE 17, 18 none
#define CARGO_PASSENGER 7
#define TYPE_DO_RAIL    0x34
#define RVA_DO_TICK     0x1C6050        // road distribution office update (game, building)
#define CTX_FUEL_MODE   0x5B0           // 2 = vehicles use fuel

static const unsigned char kDoTickPro[15] = { 0x48, 0x8B, 0xC4, 0x48, 0x89, 0x48, 0x08, 0x55, 0x53, 0x56, 0x57,
                                              0x41, 0x54, 0x41, 0x55 };
typedef void (*DoTickFn)(void* game, unsigned char* bld);
static DoTickFn g_origDoTick;
static unsigned g_fuelBypass;

static const unsigned char kCanUsePro[23] = { 0x48, 0x89, 0x5C, 0x24, 0x10, 0x48, 0x89, 0x6C, 0x24, 0x18, 0x44, 0x88,
                                              0x4C, 0x24, 0x20, 0x56, 0x57, 0x41, 0x54, 0x41, 0x55, 0x41, 0x56 };
typedef char (*CanUseFn)(void* ctx, unsigned char* bld, unsigned char* vt, char flag, void* extra);
typedef int (*GroupIdFn)(void* game, const char* name);
typedef float (*SetLengthFn)(unsigned char* vt);
static CanUseFn g_origCanUse;
static GroupIdFn g_groupId;
static SetLengthFn g_setLength;         // NULL when the bytes there are not the 1.1.1.9 function: no limits
static const unsigned char kSetLengthPro[16] = { 0x48, 0x89, 0x5C, 0x24, 0x08, 0x48, 0x83, 0xB9, 0xA0, 0x02, 0x00, 0x00,
                                                 0x00, 0x4C, 0x8B, 0xD1 };

#define RVA_MISSING_RESEARCH 0x2F76C0   // (game, building descriptor): researches blocking it -> game +0x11790
#define RVA_VEC_GROW    0x41A0          // the game's grow-by-one for that std::vector<void*> (as 0x2F76C0 calls it)
#define CTX_RESEARCH    0x11778         // std::vector of research records (0xE8 bytes: name +0, progress +0xD0)
#define CTX_BLOCKING    0x11790         // begin, end, capacity
#define CTX_NO_RESEARCH 0x1090          // set: research is off, everything is unlocked
#define RES_SIZE        0xE8
#define RES_PROGRESS    0xD0
static const unsigned char kMissingPro[18] = { 0x4C, 0x8B, 0xDC, 0x53, 0x55, 0x41, 0x57, 0x48, 0x83, 0xEC, 0x50, 0x48,
                                               0x8D, 0x99, 0x90, 0x17, 0x01, 0x00 };
typedef void (*MissingFn)(unsigned char* game, unsigned char* td);
typedef void (*VecGrowFn)(void* vec);
static MissingFn g_origMissing;
static VecGrowFn g_vecGrow;
static char g_research[64] = "railway_distribution_office";   // empty = no extra research
static int  g_researchWarned, g_gateLogged;

// limit_<object> = metres: the longest tram set that office takes
#define MAX_LIMITS 8
static struct { char object[64]; float metres; } g_limits[MAX_LIMITS];
static int g_nLimits;

static int  g_enabled = 1;
static char g_prefix[64] = "tramdo";
static int  g_logMax = 40;
static int  g_logged;
static int  g_tramGroup = -1;
static unsigned g_admitted, g_refused;

static void LogLine(const char* fmt, ...)
{
    char buf[1024];
    va_list ap; va_start(ap, fmt); vsnprintf(buf, sizeof buf, fmt, ap); va_end(ap);
    H->log("%s", buf);
}

// ---------------------------------------------------------------- settings ----

static void LoadConfig(void)
{
    char path[MAX_PATH];
    HMODULE self = NULL;
    GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT, (LPCSTR)&LoadConfig, &self);
    if (!GetModuleFileNameA(self, path, MAX_PATH)) return;
    char* dot = strrchr(path, '.');
    if (!dot) return;
    strcpy(dot, ".ini");
    FILE* f = fopen(path, "r");
    if (!f) { LogLine("tramdo  no %s - defaults", path); return; }
    char line[256];
    while (fgets(line, sizeof line, f))
    {
        char* p = line;
        while (*p == ' ' || *p == '\t') ++p;
        if (*p == ';' || *p == '#' || *p == '[' || !*p) continue;
        char* eq = strchr(p, '=');
        if (!eq) continue;
        *eq = 0;
        char* key = p; char* val = eq + 1;
        for (char* e = key + strlen(key); e > key && (e[-1] == ' ' || e[-1] == '\t'); ) *--e = 0;
        while (*val == ' ' || *val == '\t') ++val;
        for (char* e = val + strlen(val); e > val && (e[-1] == '\r' || e[-1] == '\n' || e[-1] == ' '); ) *--e = 0;
        if (!_stricmp(key, "enabled")) g_enabled = atoi(val);
        else if (!_stricmp(key, "object_prefix") && *val) strncpy(g_prefix, val, sizeof g_prefix - 1);
        else if (!_stricmp(key, "log_decisions")) g_logMax = atoi(val);
        else if (!_stricmp(key, "research")) { strncpy(g_research, val, sizeof g_research - 1); g_research[sizeof g_research - 1] = 0; }
        else if (!_strnicmp(key, "limit_", 6) && key[6] && g_nLimits < MAX_LIMITS && atof(val) > 0)
        {
            strncpy(g_limits[g_nLimits].object, key + 6, sizeof g_limits[0].object - 1);
            g_limits[g_nLimits++].metres = (float)atof(val);
        }
    }
    fclose(f);
}

// ------------------------------------------------------------------ checks ----

static int Readable(const void* p, size_t n) { return p && H->readablePtr(p, n); }

static int LooksLikePointer(const void* p)
{
    ULONG_PTR v = (ULONG_PTR)p;
    if (v < 0x10000 || v > 0x00007FFFFFFFFFFFull || (v & 7)) return 0;
    return H->readablePtr(p, 16);
}

// the object part of a building descriptor's ident ("3814373926/tramdo_small" -> "tramdo_small") and
// its building type
static const char* DescObject(unsigned char* td, int* type)
{
    if (!LooksLikePointer(td) || !Readable(td, 0x40) || !Readable(td + TD_TYPE, 4)) return NULL;
    const char* s = (const char*)td;
    int i = 0;
    for (; i < 0x40 && s[i]; ++i)
        if (s[i] < 0x20 || s[i] > 0x7E) return NULL;
    if (i < 2 || i >= 0x40) return NULL;
    *type = *(int*)(td + TD_TYPE);
    const char* slash = strrchr(s, '/');
    return slash ? slash + 1 : s;
}

// the same for a placed building
static const char* ObjectOf(unsigned char* b, int* type)
{
    if (!LooksLikePointer(b) || !Readable(b + BLD_TYPEDESC, 8)) return NULL;
    return DescObject(*(unsigned char**)(b + BLD_TYPEDESC), type);
}

static int TramGroup(void)
{
    if (g_tramGroup < 0 && g_groupId)
    {
        g_tramGroup = g_groupId(H->exeBase + RVA_GAME, "tram");
        LogLine("tramdo  train group \"tram\" = %d", g_tramGroup);
    }
    return g_tramGroup;
}

static int IsTram(unsigned char* vt)
{
    int g = TramGroup();
    if (g < 0 || !LooksLikePointer(vt) || !Readable(vt + VT_GROUPS, 16)) return 0;
    int* b = *(int**)(vt + VT_GROUPS);
    int* e = *(int**)(vt + VT_GROUPS + 8);
    if (!b || e <= b || e - b > 64 || !Readable(b, (e - b) * sizeof(int))) return 0;
    for (int* p = b; p < e; ++p)
        if (*p == g) return 1;
    return 0;
}

// a cargo tram: the tram group, and not a passenger car (every base-game tram carries passengers).
// A tram locomotive without cargo of its own (class 18) stays in: it pulls cargo wagons.
static int IsCargoTram(unsigned char* vt)
{
    if (!IsTram(vt) || !Readable(vt + VT_CARGO, 4)) return 0;
    return *(int*)(vt + VT_CARGO) != CARGO_PASSENGER;
}

static const char* Ident(unsigned char* vt)
{
    if (!LooksLikePointer(vt) || !Readable(vt + VT_IDENT, 64)) return "?";
    const char* s = (const char*)(vt + VT_IDENT);
    return memchr(s, 0, 64) ? s : "?";
}

static float LimitOf(const char* obj)
{
    for (int i = 0; i < g_nLimits; ++i)
        if (!_stricmp(obj, g_limits[i].object)) return g_limits[i].metres;
    return 0.0f;
}

// 1 / 0 for our offices, -1 for everything else
static int OfficeAnswer(unsigned char* bld, unsigned char* vt)
{
    int type = -1;
    const char* obj = ObjectOf(bld, &type);
    if (!obj || _strnicmp(obj, g_prefix, strlen(g_prefix)) != 0) return -1;
    int tram = IsCargoTram(vt);
    float limit = LimitOf(obj), length = 0.0f;
    if (tram && limit > 0.0f && g_setLength)
    {
        length = g_setLength(vt);
        if (length > limit) tram = 0;
    }
    if (g_logged < g_logMax)
    {
        ++g_logged;
        if (length > 0.0f)
            LogLine("tramdo  %s (type 0x%X) %s %s (set %.1f m, limit %.0f m)", obj, type, tram ? "admits" : "refuses",
                    Ident(vt), length, limit);
        else
            LogLine("tramdo  %s (type 0x%X) %s %s", obj, type, tram ? "admits" : "refuses", Ident(vt));
    }
    return tram;
}

static char DetourCanUse(void* ctx, unsigned char* bld, unsigned char* vt, char flag, void* extra)
{
    int answer = -1;
    __try { answer = OfficeAnswer(bld, vt); }
    __except (H->faultFilter("tramdo", GetExceptionInformation())) { answer = -1; }
    if (answer >= 0)
    {
        if (answer) ++g_admitted; else ++g_refused;
        return (char)answer;
    }
    return g_origCanUse(ctx, bld, vt, flag, extra);
}

static int IsOffice(unsigned char* bld)
{
    int type = -1;
    const char* obj = ObjectOf(bld, &type);
    return obj && _strnicmp(obj, g_prefix, strlen(g_prefix)) == 0;
}

// after the game listed what blocks a building: our offices also wait for g_research
static void AddResearchGate(unsigned char* game, unsigned char* td)
{
    if (!g_research[0] || *(unsigned char*)(game + CTX_NO_RESEARCH)) return;
    int type = -1;
    const char* obj = DescObject(td, &type);
    if (!obj || _strnicmp(obj, g_prefix, strlen(g_prefix)) != 0) return;
    unsigned char* r = *(unsigned char**)(game + CTX_RESEARCH);
    unsigned char* e = *(unsigned char**)(game + CTX_RESEARCH + 8);
    if (!r || e <= r || (e - r) % RES_SIZE || !Readable(r, e - r)) return;
    for (; r < e; r += RES_SIZE)
        if (!_stricmp((const char*)r, g_research)) break;
    if (r >= e)
    {
        if (!g_researchWarned++) LogLine("tramdo  research \"%s\" not found - offices unlock with distribution_office alone", g_research);
        return;
    }
    if (*(float*)(r + RES_PROGRESS) >= 1.0f) return;
    void*** vec = (void***)(game + CTX_BLOCKING);
    for (void** p = vec[0]; p && p < vec[1]; ++p)
        if (*p == r) return;
    if (vec[1] == vec[2]) g_vecGrow(vec);
    if (!vec[1]) return;
    *vec[1] = r;
    vec[1] += 1;
    if (!g_gateLogged++) LogLine("tramdo  %s waits for research %s", obj, g_research);
}

static void DetourMissing(unsigned char* game, unsigned char* td)
{
    g_origMissing(game, td);
    __try { AddResearchGate(game, td); }
    __except (H->faultFilter("tramdo", GetExceptionInformation())) {}
}

static void DetourDoTick(void* game, unsigned char* bld)
{
    int ours = 0;
    __try { ours = IsOffice(bld); }
    __except (H->faultFilter("tramdo", GetExceptionInformation())) { ours = 0; }
    if (!ours)
    {
        g_origDoTick(game, bld);
        return;
    }
    int* mode = (int*)((unsigned char*)game + CTX_FUEL_MODE);
    int saved = *mode;
    if (saved && g_fuelBypass++ == 0)
        LogLine("tramdo  office update: fuel mode %d off for the tram offices' own update (electric trams have no fuel level)", saved);
    *mode = 0;
    g_origDoTick(game, bld);
    *mode = saved;
}

// install an inline hook, chaining after another plugin's 14-byte absolute jump if one is there
static int Hook(unsigned rva, const unsigned char* pristine, size_t len, void* detour, void** orig, const char* label)
{
    unsigned char live[32];
    const unsigned char* expect = pristine;
    unsigned char* t = (unsigned char*)(H->exeBase + rva);
    static const unsigned char kAbsJmp[6] = { 0xFF, 0x25, 0x00, 0x00, 0x00, 0x00 };
    if (!H->readablePtr(t, len)) return 0;
    if (memcmp(t, kAbsJmp, 6) == 0)
    {
        memcpy(live, t, 14);
        expect = live; len = 14;
        LogLine("tramdo  %s: another plugin's jump is there, chaining after it", label);
    }
    else if (memcmp(t, pristine, len) != 0)
    {
        memcpy(live, t, len);
        expect = live;
        LogLine("tramdo  %s: patched by another plugin, chaining onto the live bytes", label);
    }
    return H->installInlineHook(t, detour, orig, expect, len, label);
}

// ----------------------------------------------------------------- exports ----

extern "C" __declspec(dllexport) unsigned TsmPluginApiVersion(void) { return TSM_API_VERSION; }

extern "C" __declspec(dllexport) int TsmPluginInit(const TsmHost* host, TsmPluginInfo* info)
{
    H = host;
    info->name    = "tramdo";
    info->version = "0.3";
    return 0;
}

extern "C" __declspec(dllexport) int TsmPluginStart(void)
{
    LoadConfig();
    if (!g_enabled) { LogLine("tramdo  disabled in tramdo.ini"); return 0; }
    g_groupId = (GroupIdFn)(H->exeBase + RVA_GROUP_ID);
    unsigned char* sl = (unsigned char*)(H->exeBase + RVA_SET_LENGTH);
    if (H->readablePtr(sl, sizeof kSetLengthPro) && memcmp(sl, kSetLengthPro, sizeof kSetLengthPro) == 0)
        g_setLength = (SetLengthFn)sl;
    else if (g_nLimits)
        LogLine("tramdo  set length 0x%X not recognised - length limits off, every office takes every cargo tram", RVA_SET_LENGTH);
    for (int i = 0; i < g_nLimits && g_setLength; ++i)
        LogLine("tramdo  %s takes tram sets up to %.0f m", g_limits[i].object, g_limits[i].metres);
    if (!Hook(RVA_CAN_USE, kCanUsePro, sizeof kCanUsePro, (void*)&DetourCanUse, (void**)&g_origCanUse, "tramdo CanUseBuilding"))
    {
        LogLine("tramdo  CanUseBuilding 0x%X not hooked - offices will refuse trams", RVA_CAN_USE);
        return 0;
    }
    int fuel = Hook(RVA_DO_TICK, kDoTickPro, sizeof kDoTickPro, (void*)&DetourDoTick, (void**)&g_origDoTick, "tramdo OfficeUpdate");
    if (!fuel)
        LogLine("tramdo  office update 0x%X not hooked - with fuel on, electric trams will never be dispatched", RVA_DO_TICK);
    if (g_research[0])
    {
        g_vecGrow = (VecGrowFn)(H->exeBase + RVA_VEC_GROW);
        if (Hook(RVA_MISSING_RESEARCH, kMissingPro, sizeof kMissingPro, (void*)&DetourMissing, (void**)&g_origMissing, "tramdo MissingResearch"))
            LogLine("tramdo  offices also need research %s", g_research);
        else
            LogLine("tramdo  research check 0x%X not hooked - offices unlock with distribution_office alone", RVA_MISSING_RESEARCH);
    }
    LogLine("tramdo  active: buildings named %s* take cargo trams (tram train group, not passenger), and only those; fuel bypass %s",
            g_prefix, fuel ? "on" : "OFF");
    return 0;
}
