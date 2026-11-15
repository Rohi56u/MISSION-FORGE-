import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  api,
  CDFRoom,
  CDFRoomDetail,
  CDFRole,
  CDFRevision,
  CDFEvent,
  Mission,
  getAuthToken,
  setAuthToken,
  UserProfile,
} from '../lib/api';
import {
  Users,
  Radio,
  Shield,
  History,
  AlertTriangle,
  Key,
  Copy,
  Plus,
  RefreshCw,
  Flame,
  Globe,
} from 'lucide-react';

export const CdfCollaboration: React.FC = () => {
  // Authentication & Session
  const [currentUser, setCurrentUser] = useState<UserProfile | null>(null);
  const [authEmail, setAuthEmail] = useState<string>('architect@missionforge.nasa.gov');
  const [authPassword, setAuthPassword] = useState<string>('FlightReady2026!');
  const [authName, setAuthName] = useState<string>('Dr. Elena Rostova');
  const [authError, setAuthError] = useState<string | null>(null);

  // Missions & Rooms list
  const [missions, setMissions] = useState<Mission[]>([]);
  const [rooms, setRooms] = useState<CDFRoom[]>([]);
  const [selectedRoomId, setSelectedRoomId] = useState<string | null>(null);
  const [roomDetail, setRoomDetail] = useState<CDFRoomDetail | null>(null);
  const [loadingRooms, setLoadingRooms] = useState<boolean>(false);
  const [loadingDetail, setLoadingDetail] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Room Creation Modal
  const [showCreateRoomModal, setShowCreateRoomModal] = useState<boolean>(false);
  const [newRoomName, setNewRoomName] = useState<string>('Mars Discovery CDF Room');
  const [newRoomMissionId, setNewRoomMissionId] = useState<string>('');
  const [newRoomRole, setNewRoomRole] = useState<CDFRole>('LEAD_SYSTEMS_ARCHITECT');

  // WebSocket real-time connection state
  const [wsStatus, setWsStatus] = useState<'CONNECTED' | 'CONNECTING' | 'DISCONNECTED'>('DISCONNECTED');
  const [wsReconnectTrigger, setWsReconnectTrigger] = useState<number>(0);
  const wsRef = useRef<WebSocket | null>(null);

  // Revisions & Events log
  const [revisions, setRevisions] = useState<CDFRevision[]>([]);
  const [events, setEvents] = useState<CDFEvent[]>([]);
  const [showHistoryModal, setShowHistoryModal] = useState<boolean>(false);

  // Invitation Token Modal
  const [showInviteModal, setShowInviteModal] = useState<boolean>(false);
  const [inviteRole, setInviteRole] = useState<CDFRole>('PROPULSION_POWER_OFFICER');
  const [generatedInviteToken, setGeneratedInviteToken] = useState<string | null>(null);
  const [copiedToken, setCopiedToken] = useState<boolean>(false);

  // Join with invite
  const [inviteTokenInput, setInviteTokenInput] = useState<string>('');
  const [joinInviteError, setJoinInviteError] = useState<string | null>(null);

  // Mutation form state
  const [conflictError, setConflictError] = useState<{
    message: string;
    serverVersion: number;
  } | null>(null);
  const [mutating, setMutating] = useState<boolean>(false);

  // Editable fields per role
  // Lead Architect
  const [budgetCapUsd, setBudgetCapUsd] = useState<number>(500000000);
  const [maxMassKg, setMaxMassKg] = useState<number>(1500);
  const [minDeltaVMps, setMinDeltaVMps] = useState<number>(3800);
  const [minPowerMargin, setMinPowerMargin] = useState<number>(15);

  // Propulsion & Power
  const [propellantMass, setPropellantMass] = useState<number>(450);

  // Flight Dynamics & Comms
  const [reqDeltaV, setReqDeltaV] = useState<number>(3800);
  const [distanceAu, setDistanceAu] = useState<number>(1.524);
  const [txPowerW, setTxPowerW] = useState<number>(20);
  const [dishDiameterM, setDishDiameterM] = useState<number>(1.5);

  // 1. Check current authenticated user on mount
  useEffect(() => {
    const token = getAuthToken();
    if (token) {
      api.getMe()
        .then((user) => setCurrentUser(user))
        .catch(() => {
          setAuthToken(null);
          setCurrentUser(null);
        });
    }
  }, []);

  // 2. Fetch missions and room list
  const fetchRooms = useCallback(async () => {
    setLoadingRooms(true);
    setErrorMsg(null);
    try {
      const [missionsData, roomsData] = await Promise.all([
        api.getMissions(),
        api.listCdfRooms().catch(() => []),
      ]);
      setMissions(missionsData);
      setRooms(roomsData);
      if (missionsData.length > 0 && !newRoomMissionId) {
        setNewRoomMissionId(missionsData[0].id);
      }
      if (roomsData.length > 0 && !selectedRoomId) {
        setSelectedRoomId(roomsData[0].id);
      }
    } catch (err: any) {
      setErrorMsg(err?.message || 'Failed to query active CDF rooms.');
    } finally {
      setLoadingRooms(false);
    }
  }, [newRoomMissionId, selectedRoomId]);

  useEffect(() => {
    if (currentUser) {
      fetchRooms();
    }
  }, [currentUser, fetchRooms]);

  // 3. Load selected room detail and sync form inputs
  const fetchRoomDetail = useCallback(async (roomId: string) => {
    setLoadingDetail(true);
    setConflictError(null);
    try {
      const [detail, revs, evts] = await Promise.all([
        api.getCdfRoom(roomId),
        api.listCdfRevisions(roomId).catch(() => []),
        api.listCdfEvents(roomId, 30).catch(() => []),
      ]);
      setRoomDetail(detail);
      setRevisions(revs);
      setEvents(evts);

      // Populate local form controls with authoritative state
      const state = detail.state;
      if (state) {
        setBudgetCapUsd(state.system_constraints.budget_cap_usd);
        setMaxMassKg(state.system_constraints.max_launch_mass_kg);
        setMinDeltaVMps(state.system_constraints.min_delta_v_mps);
        setMinPowerMargin(state.system_constraints.min_power_margin_percent);

        setPropellantMass(state.propulsion_and_power.propellant_mass_kg);

        setReqDeltaV(state.flight_dynamics_and_comms.required_delta_v_mps);
        setDistanceAu(state.flight_dynamics_and_comms.distance_au);
        setTxPowerW(state.flight_dynamics_and_comms.tx_power_w);
        setDishDiameterM(state.flight_dynamics_and_comms.antenna_diameter_m);
      }
    } catch (err: any) {
      setErrorMsg(err?.message || 'Failed to retrieve room authoritative state.');
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  useEffect(() => {
    if (selectedRoomId && currentUser) {
      fetchRoomDetail(selectedRoomId);
    }
  }, [selectedRoomId, currentUser, fetchRoomDetail]);

  // 4. WebSocket setup for real-time room synchronization
  useEffect(() => {
    if (!selectedRoomId || !currentUser) return;
    const token = getAuthToken();
    if (!token) return;

    let isDisposed = false;
    let pingInterval: ReturnType<typeof setInterval> | null = null;
    let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
    let reconnectAttempts = 0;
    const MAX_RECONNECT_ATTEMPTS = 5;

    const connectWs = () => {
      if (isDisposed) return;
      // Use current browser host with ws / wss protocol
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host;
      const wsUrl = `${protocol}//${host}/api/v1/cdf/ws/${encodeURIComponent(selectedRoomId)}?token=${encodeURIComponent(token)}`;

      setWsStatus('CONNECTING');
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (isDisposed) {
          ws.close(1000, 'Unmounted');
          return;
        }
        setWsStatus('CONNECTED');
        reconnectAttempts = 0;

        // Periodic keepalive ping every 30s to keep connection active and satisfy 120s server timeout
        if (pingInterval) clearInterval(pingInterval);
        pingInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            try {
              ws.send(JSON.stringify({ action: 'PING' }));
            } catch {
              // ignore transient send failures
            }
          }
        }, 30000);
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (
            msg.type === 'STATE_UPDATED' ||
            msg.type === 'PARTICIPANT_JOINED' ||
            msg.type === 'PARTICIPANT_LEFT' ||
            msg.type === 'ROOM_JOINED' ||
            msg.type === 'CONSTRAINT_ALERT'
          ) {
            // Refresh room state when server broadcasts change
            fetchRoomDetail(selectedRoomId);
          }
        } catch (e) {
          console.error('Failed to parse WS message', e);
        }
      };

      ws.onclose = (event) => {
        if (pingInterval) clearInterval(pingInterval);
        if (isDisposed) return;
        setWsStatus('DISCONNECTED');

        // Automatically reconnect with exponential backoff if not closed cleanly
        if (event.code !== 1000 && reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
          reconnectAttempts += 1;
          const delay = Math.min(1000 * Math.pow(2, reconnectAttempts - 1), 8000);
          reconnectTimeout = setTimeout(connectWs, delay);
        }
      };

      ws.onerror = () => {
        if (!isDisposed) {
          setWsStatus('DISCONNECTED');
        }
      };
    };

    connectWs();

    return () => {
      isDisposed = true;
      if (pingInterval) clearInterval(pingInterval);
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (wsRef.current) {
        wsRef.current.close(1000, 'Component unmounted');
        wsRef.current = null;
      }
    };
  }, [selectedRoomId, currentUser, fetchRoomDetail, wsReconnectTrigger]);

  // Current participant info for current user in active room
  const currentParticipant = React.useMemo(() => {
    if (!roomDetail || !currentUser) return null;
    return roomDetail.participants.find((p) => p.user_id === currentUser.id) || null;
  }, [roomDetail, currentUser]);

  // User Authentication Handlers
  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError(null);
    try {
      const res = await api.login(authEmail, authPassword);
      setAuthToken(res.access_token);
      setCurrentUser(res.user);
    } catch (err: any) {
      setAuthError(err?.message || 'Login failed. Verify credentials.');
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError(null);
    try {
      const res = await api.register(authEmail, authPassword, authName);
      setAuthToken(res.access_token);
      setCurrentUser(res.user);
    } catch (err: any) {
      setAuthError(err?.message || 'Registration failed.');
    }
  };

  // Create Room Handler
  const handleCreateRoom = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newRoomName || !newRoomMissionId) return;
    try {
      const room = await api.createCdfRoom(newRoomName, newRoomMissionId, newRoomRole);
      setShowCreateRoomModal(false);
      setRooms((prev) => [room, ...prev]);
      setSelectedRoomId(room.id);
    } catch (err: any) {
      setErrorMsg(err?.message || 'Failed to create CDF room.');
    }
  };

  // Join Room Handler
  const handleJoinRole = async (role: CDFRole) => {
    if (!selectedRoomId) return;
    try {
      await api.joinCdfRoom(selectedRoomId, role);
      fetchRoomDetail(selectedRoomId);
    } catch (err: any) {
      setErrorMsg(err?.message || `Failed to join room under role ${role}.`);
    }
  };

  // Submit Mutation Handler
  const handleMutate = async (
    category: 'SYSTEM_CONSTRAINTS' | 'PROPULSION_POWER' | 'SCIENCE_PAYLOAD' | 'FLIGHT_DYNAMICS_COMMS',
    patchData: Record<string, any>
  ) => {
    if (!selectedRoomId || !roomDetail) return;
    setMutating(true);
    setConflictError(null);
    try {
      const res = await api.mutateCdfState(selectedRoomId, {
        base_version: roomDetail.current_version,
        mutation_category: category,
        patch_data: patchData,
        client_message_id: `msg-${Date.now()}`,
      });
      // Update room state directly from response
      setRoomDetail((prev) =>
        prev
          ? {
              ...prev,
              current_version: res.new_version,
              state: res.state,
            }
          : null
      );
    } catch (err: any) {
      if (err.status === 409 || err.data?.detail?.error === 'VERSION_CONFLICT') {
        const servVer = err.data?.detail?.current_version || roomDetail.current_version + 1;
        setConflictError({
          message: 'Concurrent version conflict detected. Another participant submitted a newer revision.',
          serverVersion: servVer,
        });
      } else {
        setErrorMsg(err?.message || 'Design mutation rejected by server validation.');
      }
    } finally {
      setMutating(false);
    }
  };

  // Invitation Token Generator
  const handleGenerateInvite = async () => {
    if (!selectedRoomId) return;
    try {
      const res = await api.createCdfInvitation(selectedRoomId, inviteRole);
      setGeneratedInviteToken(res.invite_token);
      setCopiedToken(false);
    } catch (err: any) {
      setErrorMsg(err?.message || 'Failed to create room invitation.');
    }
  };

  // Join with invite token
  const handleJoinWithInvite = async () => {
    if (!inviteTokenInput.trim()) return;
    setJoinInviteError(null);
    try {
      await api.joinCdfWithInvite(inviteTokenInput.trim());
      setInviteTokenInput('');
      fetchRooms();
    } catch (err: any) {
      setJoinInviteError(err?.message || 'Invalid or expired invitation token.');
    }
  };

  // If user is not authenticated, show authentication prompt banner
  if (!currentUser) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-16 text-center font-mono space-y-6">
        <div className="p-4 bg-panel border border-hairline rounded-lg shadow-panel max-w-md mx-auto">
          <Users className="w-12 h-12 text-accent mx-auto mb-3" />
          <h2 className="text-lg font-bold text-white uppercase tracking-wider">
            Concurrent Design Facility (CDF)
          </h2>
          <p className="text-xs text-slate-400 mt-2">
            Secure multi-user aerospace engineering collaboration requires authenticated operator credentials.
          </p>

          {authError && (
            <div className="mt-4 p-2.5 bg-red-950/80 border border-red-800 text-red-200 text-xs rounded text-left">
              {authError}
            </div>
          )}

          <form onSubmit={handleLogin} className="mt-5 space-y-3 text-left text-xs">
            <div>
              <label className="text-slate-400 block mb-1">Operator Email:</label>
              <input
                type="email"
                value={authEmail}
                onChange={(e) => setAuthEmail(e.target.value)}
                className="w-full px-3 py-1.5 bg-slate-900 border border-hairline rounded text-white focus:outline-none focus:border-accent"
                required
              />
            </div>
            <div>
              <label className="text-slate-400 block mb-1">Password:</label>
              <input
                type="password"
                value={authPassword}
                onChange={(e) => setAuthPassword(e.target.value)}
                className="w-full px-3 py-1.5 bg-slate-900 border border-hairline rounded text-white focus:outline-none focus:border-accent"
                required
              />
            </div>
            <div>
              <label className="text-slate-400 block mb-1">Operator Full Name (for registration):</label>
              <input
                type="text"
                value={authName}
                onChange={(e) => setAuthName(e.target.value)}
                className="w-full px-3 py-1.5 bg-slate-900 border border-hairline rounded text-white focus:outline-none focus:border-accent"
              />
            </div>

            <div className="flex items-center space-x-2 pt-2">
              <button
                type="submit"
                className="flex-1 py-2 bg-accent text-canvas font-semibold rounded hover:bg-accent/90"
              >
                LOGIN
              </button>
              <button
                type="button"
                onClick={handleRegister}
                className="flex-1 py-2 bg-panel-raised border border-hairline text-slate-300 font-semibold rounded hover:text-white"
              >
                REGISTER
              </button>
            </div>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      {/* Header Bar */}
      <div className="bg-panel border border-hairline rounded-lg p-5 shadow-panel flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <Users className="w-5 h-5 text-accent" />
            <h1 className="text-xl font-bold font-mono tracking-wider text-white uppercase">
              Phase 11 — Concurrent Design Facility (CDF)
            </h1>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Real-time collaborative concurrent design environment supporting 4 specialized engineering roles.
          </p>
        </div>

        {/* Room Switcher & Create Button */}
        <div className="flex flex-wrap items-center gap-2 text-xs font-mono">
          {(loadingRooms || loadingDetail) && (
            <RefreshCw className="w-4 h-4 text-accent animate-spin" />
          )}

          <select
            value={selectedRoomId || ''}
            onChange={(e) => setSelectedRoomId(e.target.value)}
            className="px-3 py-1.5 bg-slate-900 border border-hairline rounded text-white focus:outline-none focus:border-accent"
            aria-label="Select CDF Room"
          >
            {rooms.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name} (v{r.current_version} • {r.status})
              </option>
            ))}
          </select>

          <button
            onClick={() => setShowCreateRoomModal(true)}
            className="px-3 py-1.5 rounded bg-accent/20 border border-accent/60 text-accent font-semibold hover:bg-accent/30 flex items-center space-x-1"
            aria-label="Create new CDF room"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>NEW ROOM</span>
          </button>

          {/* Join with Invite Token Field */}
          <div className="flex items-center space-x-1">
            <input
              type="text"
              placeholder="Invite token..."
              value={inviteTokenInput}
              onChange={(e) => setInviteTokenInput(e.target.value)}
              className="px-2 py-1 bg-slate-900 border border-hairline rounded text-white text-xs w-28"
            />
            <button
              onClick={handleJoinWithInvite}
              className="px-2 py-1 bg-panel-raised border border-hairline text-slate-300 hover:text-white rounded"
            >
              JOIN INVITE
            </button>
          </div>
        </div>
      </div>

      {joinInviteError && (
        <div role="alert" className="p-2 bg-red-950/80 border border-red-800 text-red-200 text-xs font-mono rounded">
          {joinInviteError}
        </div>
      )}

      {errorMsg && (
        <div role="alert" className="p-3 bg-red-950/80 border border-red-800 text-red-200 text-xs font-mono rounded">
          {errorMsg}
        </div>
      )}

      {/* Room Status & Real-Time Sync Bar */}
      {roomDetail && (
        <div className="bg-slate-900/90 border border-hairline rounded-lg p-4 flex flex-wrap items-center justify-between gap-4 text-xs font-mono">
          <div className="flex items-center space-x-4">
            <div>
              <span className="text-slate-500">ROOM:</span>{' '}
              <span className="text-white font-semibold">{roomDetail.name}</span>
            </div>
            <div>
              <span className="text-slate-500">VERSION:</span>{' '}
              <span className="text-accent font-semibold tabular-nums">v{roomDetail.current_version}</span>
            </div>
            <div>
              <span className="text-slate-500">STATUS:</span>{' '}
              <span className="text-emerald-400 font-semibold">{roomDetail.status}</span>
            </div>
          </div>

          <div className="flex items-center space-x-3">
            {/* Real-Time WebSocket Presence Badge */}
            <div
              className="flex items-center space-x-1.5 px-2.5 py-1 rounded border text-[11px]"
              title={`WebSocket state: ${wsStatus}`}
            >
              <span
                className={`w-2 h-2 rounded-full ${
                  wsStatus === 'CONNECTED'
                    ? 'bg-emerald-400 animate-pulse'
                    : wsStatus === 'CONNECTING'
                    ? 'bg-amber-400 animate-spin'
                    : 'bg-slate-500'
                }`}
              />
              <span className="text-slate-300">
                {wsStatus === 'CONNECTED' ? 'LIVE SYNC' : wsStatus === 'CONNECTING' ? 'CONNECTING' : 'OFFLINE'}
              </span>
              {wsStatus === 'DISCONNECTED' && (
                <button
                  onClick={() => setWsReconnectTrigger((t) => t + 1)}
                  className="ml-1 text-[10px] text-accent hover:underline flex items-center space-x-0.5"
                  title="Reconnect to room WebSocket"
                  aria-label="Reconnect WebSocket"
                >
                  <RefreshCw className="w-2.5 h-2.5" />
                  <span>RECONNECT</span>
                </button>
              )}
            </div>

            {/* Operator Role Badge */}
            <div className="px-2.5 py-1 bg-panel border border-hairline rounded text-[11px] text-slate-300">
              <span className="text-slate-500">MY ROLE:</span>{' '}
              <span className="text-white font-semibold">
                {currentParticipant ? currentParticipant.role.replace(/_/g, ' ') : 'OBSERVER / UNASSIGNED'}
              </span>
            </div>

            {/* Revisions & History Button */}
            <button
              onClick={() => setShowHistoryModal(true)}
              className="p-1.5 rounded bg-panel border border-hairline text-slate-300 hover:text-white"
              title="Audit trail & version history"
              aria-label="View room revision history"
            >
              <History className="w-3.5 h-3.5" />
            </button>

            {/* Invitations Button */}
            <button
              onClick={() => setShowInviteModal(true)}
              className="p-1.5 rounded bg-panel border border-hairline text-slate-300 hover:text-white"
              title="Invite participant to room"
              aria-label="Generate room invitation"
            >
              <Key className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}

      {/* Version Conflict Modal / Alert */}
      {conflictError && (
        <div
          role="alert"
          className="p-4 bg-amber-950/80 border border-amber-800 rounded-lg text-xs font-mono text-amber-200 flex items-center justify-between gap-4"
        >
          <div className="flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0" />
            <div>
              <div className="font-semibold">{conflictError.message}</div>
              <div className="text-[11px] text-amber-300 mt-0.5">
                Server authoritative state is currently at version {conflictError.serverVersion}.
              </div>
            </div>
          </div>
          <button
            onClick={() => selectedRoomId && fetchRoomDetail(selectedRoomId)}
            className="px-3 py-1.5 bg-amber-500 text-slate-950 font-semibold rounded hover:bg-amber-400 flex items-center space-x-1"
          >
            <RefreshCw className="w-3 h-3" />
            <span>RESYNC AUTHORITATIVE STATE</span>
          </button>
        </div>
      )}

      {/* Participant Roster Bar */}
      {roomDetail && (
        <div className="bg-panel border border-hairline rounded-lg p-4 shadow-panel">
          <div className="text-xs font-mono font-semibold text-slate-400 uppercase tracking-wider mb-2">
            Concurrent Design Roster ({roomDetail.participants.length}/{roomDetail.max_participants} Participants)
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
            {roomDetail.participants.map((p) => (
              <div
                key={p.id}
                className={`p-2.5 rounded border text-xs font-mono ${
                  p.user_id === currentUser.id
                    ? 'bg-accent/10 border-accent text-white'
                    : 'bg-slate-900 border-hairline text-slate-300'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold truncate">{p.full_name}</span>
                  <span
                    className={`w-2 h-2 rounded-full ${
                      p.is_connected ? 'bg-emerald-400' : 'bg-slate-600'
                    }`}
                    title={p.is_connected ? 'Connected' : 'Offline'}
                  />
                </div>
                <div className="text-[10px] text-accent mt-0.5">{p.role.replace(/_/g, ' ')}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Authoritative Calculated Budgets & Alerts HUD */}
      {roomDetail?.state?.calculated_budgets && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs font-mono">
          <div className="bg-panel border border-hairline rounded-lg p-3.5 shadow-panel">
            <span className="text-slate-400 uppercase text-[10px]">Mass Margin</span>
            <div className="text-lg font-bold text-white tabular-nums">
              {roomDetail.state.calculated_budgets.mass_margin_percent.toFixed(1)}%
            </div>
            <div className="text-[10px] text-slate-500 mt-0.5">
              Wet: {roomDetail.state.calculated_budgets.wet_mass_kg.toFixed(0)} kg
            </div>
          </div>

          <div className="bg-panel border border-hairline rounded-lg p-3.5 shadow-panel">
            <span className="text-slate-400 uppercase text-[10px]">Power Margin</span>
            <div className="text-lg font-bold text-white tabular-nums">
              {roomDetail.state.calculated_budgets.power_margin_percent.toFixed(1)}%
            </div>
            <div className="text-[10px] text-slate-500 mt-0.5">
              Draw: {roomDetail.state.calculated_budgets.total_power_draw_w.toFixed(0)} W
            </div>
          </div>

          <div className="bg-panel border border-hairline rounded-lg p-3.5 shadow-panel">
            <span className="text-slate-400 uppercase text-[10px]">Delta-V Available</span>
            <div className="text-lg font-bold text-white tabular-nums">
              {Math.round(roomDetail.state.calculated_budgets.available_delta_v_mps)} m/s
            </div>
            <div className="text-[10px] text-slate-500 mt-0.5">
              Margin: {roomDetail.state.calculated_budgets.delta_v_margin_percent.toFixed(1)}%
            </div>
          </div>

          <div className="bg-panel border border-hairline rounded-lg p-3.5 shadow-panel">
            <span className="text-slate-400 uppercase text-[10px]">Cost Budget</span>
            <div className="text-lg font-bold text-white tabular-nums">
              ${(roomDetail.state.calculated_budgets.total_cost_usd / 1e6).toFixed(1)}M
            </div>
            <div className="text-[10px] text-slate-500 mt-0.5">
              Margin: {roomDetail.state.calculated_budgets.cost_margin_percent.toFixed(1)}%
            </div>
          </div>
        </div>
      )}

      {/* Active Constraint Alerts Banner */}
      {roomDetail?.state?.constraint_alerts && roomDetail.state.constraint_alerts.length > 0 && (
        <div className="bg-panel border border-amber-900/60 rounded-lg p-4 shadow-panel space-y-2">
          <div className="text-xs font-mono font-semibold text-amber-400 uppercase tracking-wider">
            CDF Real-Time Constraint Alerts ({roomDetail.state.constraint_alerts.length}):
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {roomDetail.state.constraint_alerts.map((alert, idx) => (
              <div key={idx} className="p-2.5 bg-amber-950/30 border border-amber-800/50 rounded text-xs font-mono">
                <div className="flex items-center justify-between text-amber-300 font-semibold">
                  <span>{alert.alert_code}</span>
                  <span className="text-[10px] px-1.5 py-0.2 rounded bg-amber-900 text-amber-100">{alert.severity}</span>
                </div>
                <div className="text-slate-300 text-[11px] mt-1">{alert.message}</div>
                <div className="text-accent text-[10px] mt-1 font-medium">Action: {alert.actionable_guidance}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* The 4 Role Collaboration Stations Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Role 1: Lead Systems Architect Station */}
        <div
          className={`bg-panel border rounded-lg p-5 shadow-panel flex flex-col space-y-3 ${
            currentParticipant?.role === 'LEAD_SYSTEMS_ARCHITECT'
              ? 'border-accent ring-1 ring-accent'
              : 'border-hairline'
          }`}
        >
          <div className="flex items-center justify-between border-b border-hairline pb-2.5">
            <div className="flex items-center space-x-2">
              <Shield className="w-4 h-4 text-accent" />
              <h3 className="font-mono font-semibold text-sm text-white uppercase">
                Lead Systems Architect
              </h3>
            </div>
            {currentParticipant?.role !== 'LEAD_SYSTEMS_ARCHITECT' && (
              <button
                onClick={() => handleJoinRole('LEAD_SYSTEMS_ARCHITECT')}
                className="text-[11px] font-mono px-2 py-0.5 rounded bg-panel-raised border border-hairline text-slate-300 hover:text-white"
              >
                Assume Role
              </button>
            )}
          </div>

          <div className="space-y-3 text-xs font-mono">
            <div>
              <label className="text-slate-400 block mb-1">Budget Cap (USD):</label>
              <input
                type="number"
                value={budgetCapUsd}
                onChange={(e) => setBudgetCapUsd(Number(e.target.value))}
                disabled={currentParticipant?.role !== 'LEAD_SYSTEMS_ARCHITECT'}
                className="w-full px-3 py-1.5 bg-slate-900 border border-hairline rounded text-white focus:outline-none focus:border-accent disabled:opacity-50"
              />
            </div>
            <div>
              <label className="text-slate-400 block mb-1">Max Launch Mass (kg):</label>
              <input
                type="number"
                value={maxMassKg}
                onChange={(e) => setMaxMassKg(Number(e.target.value))}
                disabled={currentParticipant?.role !== 'LEAD_SYSTEMS_ARCHITECT'}
                className="w-full px-3 py-1.5 bg-slate-900 border border-hairline rounded text-white focus:outline-none focus:border-accent disabled:opacity-50"
              />
            </div>
            <div>
              <label className="text-slate-400 block mb-1">Min Delta-V (m/s):</label>
              <input
                type="number"
                value={minDeltaVMps}
                onChange={(e) => setMinDeltaVMps(Number(e.target.value))}
                disabled={currentParticipant?.role !== 'LEAD_SYSTEMS_ARCHITECT'}
                className="w-full px-3 py-1.5 bg-slate-900 border border-hairline rounded text-white focus:outline-none focus:border-accent disabled:opacity-50"
              />
            </div>
            <div>
              <label className="text-slate-400 block mb-1">Min Power Margin (%):</label>
              <input
                type="number"
                value={minPowerMargin}
                onChange={(e) => setMinPowerMargin(Number(e.target.value))}
                disabled={currentParticipant?.role !== 'LEAD_SYSTEMS_ARCHITECT'}
                className="w-full px-3 py-1.5 bg-slate-900 border border-hairline rounded text-white focus:outline-none focus:border-accent disabled:opacity-50"
              />
            </div>

            {currentParticipant?.role === 'LEAD_SYSTEMS_ARCHITECT' && (
              <button
                onClick={() =>
                  handleMutate('SYSTEM_CONSTRAINTS', {
                    budget_cap_usd: budgetCapUsd,
                    max_launch_mass_kg: maxMassKg,
                    min_delta_v_mps: minDeltaVMps,
                    min_power_margin_percent: minPowerMargin,
                  })
                }
                disabled={mutating}
                className="w-full py-2 bg-accent text-canvas font-semibold rounded hover:bg-accent/90"
              >
                {mutating ? 'COMMITTING...' : 'COMMIT SYSTEM CONSTRAINTS'}
              </button>
            )}
          </div>
        </div>

        {/* Role 2: Propulsion & Power Officer Station */}
        <div
          className={`bg-panel border rounded-lg p-5 shadow-panel flex flex-col space-y-3 ${
            currentParticipant?.role === 'PROPULSION_POWER_OFFICER'
              ? 'border-accent ring-1 ring-accent'
              : 'border-hairline'
          }`}
        >
          <div className="flex items-center justify-between border-b border-hairline pb-2.5">
            <div className="flex items-center space-x-2">
              <Flame className="w-4 h-4 text-amber-400" />
              <h3 className="font-mono font-semibold text-sm text-white uppercase">
                Propulsion & Power Officer
              </h3>
            </div>
            {currentParticipant?.role !== 'PROPULSION_POWER_OFFICER' && (
              <button
                onClick={() => handleJoinRole('PROPULSION_POWER_OFFICER')}
                className="text-[11px] font-mono px-2 py-0.5 rounded bg-panel-raised border border-hairline text-slate-300 hover:text-white"
              >
                Assume Role
              </button>
            )}
          </div>

          <div className="space-y-3 text-xs font-mono">
            <div>
              <label className="text-slate-400 block mb-1">Sized Propellant Mass (kg):</label>
              <input
                type="number"
                value={propellantMass}
                onChange={(e) => setPropellantMass(Number(e.target.value))}
                disabled={currentParticipant?.role !== 'PROPULSION_POWER_OFFICER'}
                className="w-full px-3 py-1.5 bg-slate-900 border border-hairline rounded text-white focus:outline-none focus:border-accent disabled:opacity-50"
              />
            </div>

            <div className="p-3 bg-slate-900/80 border border-hairline rounded text-[11px] text-slate-400">
              Allocated Propellant directly sizes wet mass and delta-V according to Tsiolkovsky's equation.
            </div>

            {currentParticipant?.role === 'PROPULSION_POWER_OFFICER' && (
              <button
                onClick={() =>
                  handleMutate('PROPULSION_POWER', {
                    propellant_mass_kg: propellantMass,
                  })
                }
                disabled={mutating}
                className="w-full py-2 bg-accent text-canvas font-semibold rounded hover:bg-accent/90"
              >
                {mutating ? 'COMMITTING...' : 'COMMIT PROPULSION MUTATION'}
              </button>
            )}
          </div>
        </div>

        {/* Role 3: Science Officer Station */}
        <div
          className={`bg-panel border rounded-lg p-5 shadow-panel flex flex-col space-y-3 ${
            currentParticipant?.role === 'SCIENCE_OFFICER'
              ? 'border-accent ring-1 ring-accent'
              : 'border-hairline'
          }`}
        >
          <div className="flex items-center justify-between border-b border-hairline pb-2.5">
            <div className="flex items-center space-x-2">
              <Globe className="w-4 h-4 text-emerald-400" />
              <h3 className="font-mono font-semibold text-sm text-white uppercase">
                Science Officer
              </h3>
            </div>
            {currentParticipant?.role !== 'SCIENCE_OFFICER' && (
              <button
                onClick={() => handleJoinRole('SCIENCE_OFFICER')}
                className="text-[11px] font-mono px-2 py-0.5 rounded bg-panel-raised border border-hairline text-slate-300 hover:text-white"
              >
                Assume Role
              </button>
            )}
          </div>

          <div className="space-y-3 text-xs font-mono">
            <div className="p-3 bg-slate-900/80 border border-hairline rounded text-[11px] text-slate-400">
              Science Officer defines observation payload instruments, detector mass, and power budgets.
            </div>

            {currentParticipant?.role === 'SCIENCE_OFFICER' && (
              <button
                onClick={() =>
                  handleMutate('SCIENCE_PAYLOAD', {
                    components: [
                      {
                        name: 'Multispectral Scientific Imager',
                        subsystem: 'SCIENCE',
                        mass_kg: 18.5,
                        power_draw_w: 32.0,
                        cost_usd: 12000000,
                      },
                    ],
                  })
                }
                disabled={mutating}
                className="w-full py-2 bg-accent text-canvas font-semibold rounded hover:bg-accent/90"
              >
                {mutating ? 'COMMITTING...' : 'UPDATE SCIENCE INSTRUMENTS'}
              </button>
            )}
          </div>
        </div>

        {/* Role 4: Flight Dynamics & Comms Officer Station */}
        <div
          className={`bg-panel border rounded-lg p-5 shadow-panel flex flex-col space-y-3 ${
            currentParticipant?.role === 'FLIGHT_DYNAMICS_COMMS_OFFICER'
              ? 'border-accent ring-1 ring-accent'
              : 'border-hairline'
          }`}
        >
          <div className="flex items-center justify-between border-b border-hairline pb-2.5">
            <div className="flex items-center space-x-2">
              <Radio className="w-4 h-4 text-sky-400" />
              <h3 className="font-mono font-semibold text-sm text-white uppercase">
                Flight Dynamics & Comms Officer
              </h3>
            </div>
            {currentParticipant?.role !== 'FLIGHT_DYNAMICS_COMMS_OFFICER' && (
              <button
                onClick={() => handleJoinRole('FLIGHT_DYNAMICS_COMMS_OFFICER')}
                className="text-[11px] font-mono px-2 py-0.5 rounded bg-panel-raised border border-hairline text-slate-300 hover:text-white"
              >
                Assume Role
              </button>
            )}
          </div>

          <div className="space-y-3 text-xs font-mono">
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-slate-400 block mb-1">Target Distance (AU):</label>
                <input
                  type="number"
                  step="0.01"
                  value={distanceAu}
                  onChange={(e) => setDistanceAu(Number(e.target.value))}
                  disabled={currentParticipant?.role !== 'FLIGHT_DYNAMICS_COMMS_OFFICER'}
                  className="w-full px-3 py-1.5 bg-slate-900 border border-hairline rounded text-white focus:outline-none focus:border-accent disabled:opacity-50"
                />
              </div>
              <div>
                <label className="text-slate-400 block mb-1">Tx RF Power (W):</label>
                <input
                  type="number"
                  value={txPowerW}
                  onChange={(e) => setTxPowerW(Number(e.target.value))}
                  disabled={currentParticipant?.role !== 'FLIGHT_DYNAMICS_COMMS_OFFICER'}
                  className="w-full px-3 py-1.5 bg-slate-900 border border-hairline rounded text-white focus:outline-none focus:border-accent disabled:opacity-50"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-slate-400 block mb-1">Required Delta-V (m/s):</label>
                <input
                  type="number"
                  value={reqDeltaV}
                  onChange={(e) => setReqDeltaV(Number(e.target.value))}
                  disabled={currentParticipant?.role !== 'FLIGHT_DYNAMICS_COMMS_OFFICER'}
                  className="w-full px-3 py-1.5 bg-slate-900 border border-hairline rounded text-white focus:outline-none focus:border-accent disabled:opacity-50"
                />
              </div>
              <div>
                <label className="text-slate-400 block mb-1">Dish Diameter (m):</label>
                <input
                  type="number"
                  step="0.1"
                  value={dishDiameterM}
                  onChange={(e) => setDishDiameterM(Number(e.target.value))}
                  disabled={currentParticipant?.role !== 'FLIGHT_DYNAMICS_COMMS_OFFICER'}
                  className="w-full px-3 py-1.5 bg-slate-900 border border-hairline rounded text-white focus:outline-none focus:border-accent disabled:opacity-50"
                />
              </div>
            </div>

            {currentParticipant?.role === 'FLIGHT_DYNAMICS_COMMS_OFFICER' && (
              <button
                onClick={() =>
                  handleMutate('FLIGHT_DYNAMICS_COMMS', {
                    distance_au: distanceAu,
                    tx_power_w: txPowerW,
                    antenna_diameter_m: dishDiameterM,
                    required_delta_v_mps: reqDeltaV,
                  })
                }
                disabled={mutating}
                className="w-full py-2 bg-accent text-canvas font-semibold rounded hover:bg-accent/90"
              >
                {mutating ? 'COMMITTING...' : 'COMMIT COMMS MUTATION'}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Revision History & Event Log Drawer / Modal */}
      {showHistoryModal && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-panel border border-hairline rounded-lg max-w-2xl w-full p-6 space-y-4 shadow-panel font-mono text-xs">
            <div className="flex items-center justify-between border-b border-hairline pb-3">
              <h3 className="text-sm font-semibold text-white uppercase tracking-wider">
                CDF Version Revisions & Audit Log
              </h3>
              <button
                onClick={() => setShowHistoryModal(false)}
                className="text-slate-400 hover:text-white"
              >
                CLOSE
              </button>
            </div>

            <div className="space-y-4 max-h-[400px] overflow-y-auto pr-2">
              <div>
                <div className="text-accent font-semibold mb-2">Committed Revisions ({revisions.length}):</div>
                <div className="space-y-2">
                  {revisions.map((rev) => (
                    <div key={rev.id} className="p-2.5 bg-slate-900 border border-hairline rounded text-[11px]">
                      <div className="flex items-center justify-between text-white font-semibold">
                        <span>Revision v{rev.version} — {rev.mutation_type}</span>
                        <span className="text-slate-500">{new Date(rev.created_at).toLocaleTimeString()}</span>
                      </div>
                      <div className="text-slate-400 text-[10px] mt-1">Author Role: {rev.author_role}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <div className="text-slate-400 font-semibold mb-2">Audit Events Log:</div>
                <div className="space-y-1.5">
                  {events.map((evt) => (
                    <div key={evt.id} className="p-2 bg-slate-900/60 border border-hairline/60 rounded text-[10px] text-slate-300">
                      <span className="text-slate-500">[{new Date(evt.created_at).toLocaleTimeString()}]</span>{' '}
                      <span className="text-accent font-semibold">{evt.event_type}</span> — v{evt.version} by {evt.actor_role || 'System'}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Invitation Token Generator Modal */}
      {showInviteModal && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-panel border border-hairline rounded-lg max-w-md w-full p-6 space-y-4 shadow-panel font-mono text-xs">
            <div className="flex items-center justify-between border-b border-hairline pb-3">
              <h3 className="text-sm font-semibold text-white uppercase tracking-wider">
                Generate Role Invitation Token
              </h3>
              <button
                onClick={() => setShowInviteModal(false)}
                className="text-slate-400 hover:text-white"
              >
                CLOSE
              </button>
            </div>

            <div>
              <label className="text-slate-400 block mb-1">Target Engineering Role:</label>
              <select
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value as CDFRole)}
                className="w-full px-3 py-1.5 bg-slate-900 border border-hairline rounded text-white"
              >
                <option value="PROPULSION_POWER_OFFICER">Propulsion & Power Officer</option>
                <option value="SCIENCE_OFFICER">Science Officer</option>
                <option value="FLIGHT_DYNAMICS_COMMS_OFFICER">Flight Dynamics & Comms Officer</option>
                <option value="LEAD_SYSTEMS_ARCHITECT">Lead Systems Architect</option>
              </select>
            </div>

            <button
              onClick={handleGenerateInvite}
              className="w-full py-2 bg-accent text-canvas font-semibold rounded hover:bg-accent/90"
            >
              GENERATE CRYPTOGRAPHIC TOKEN
            </button>

            {generatedInviteToken && (
              <div className="p-3 bg-slate-900 border border-accent/40 rounded space-y-2">
                <div className="text-[10px] text-slate-400">Signed Token:</div>
                <textarea
                  readOnly
                  value={generatedInviteToken}
                  rows={3}
                  className="w-full bg-slate-950 p-2 rounded text-[10px] text-accent border border-hairline"
                />
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(generatedInviteToken);
                    setCopiedToken(true);
                  }}
                  className="w-full py-1.5 rounded bg-panel-raised border border-hairline text-slate-300 hover:text-white flex items-center justify-center space-x-1"
                >
                  <Copy className="w-3 h-3" />
                  <span>{copiedToken ? 'COPIED TO CLIPBOARD' : 'COPY TOKEN'}</span>
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Create Room Modal */}
      {showCreateRoomModal && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <form onSubmit={handleCreateRoom} className="bg-panel border border-hairline rounded-lg max-w-md w-full p-6 space-y-4 shadow-panel font-mono text-xs">
            <div className="flex items-center justify-between border-b border-hairline pb-3">
              <h3 className="text-sm font-semibold text-white uppercase tracking-wider">
                Create Collaborative CDF Room
              </h3>
              <button
                type="button"
                onClick={() => setShowCreateRoomModal(false)}
                className="text-slate-400 hover:text-white"
              >
                CLOSE
              </button>
            </div>

            <div>
              <label className="text-slate-400 block mb-1">Room Name:</label>
              <input
                type="text"
                value={newRoomName}
                onChange={(e) => setNewRoomName(e.target.value)}
                required
                className="w-full px-3 py-1.5 bg-slate-900 border border-hairline rounded text-white focus:outline-none focus:border-accent"
              />
            </div>

            <div>
              <label className="text-slate-400 block mb-1">Target Mission:</label>
              <select
                value={newRoomMissionId}
                onChange={(e) => setNewRoomMissionId(e.target.value)}
                className="w-full px-3 py-1.5 bg-slate-900 border border-hairline rounded text-white"
              >
                {missions.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name} ({m.target})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-slate-400 block mb-1">Your Creator Role:</label>
              <select
                value={newRoomRole}
                onChange={(e) => setNewRoomRole(e.target.value as CDFRole)}
                className="w-full px-3 py-1.5 bg-slate-900 border border-hairline rounded text-white"
              >
                <option value="LEAD_SYSTEMS_ARCHITECT">Lead Systems Architect</option>
                <option value="PROPULSION_POWER_OFFICER">Propulsion & Power Officer</option>
                <option value="SCIENCE_OFFICER">Science Officer</option>
                <option value="FLIGHT_DYNAMICS_COMMS_OFFICER">Flight Dynamics & Comms Officer</option>
              </select>
            </div>

            <button
              type="submit"
              className="w-full py-2 bg-accent text-canvas font-semibold rounded hover:bg-accent/90"
            >
              INITIALIZE ROOM
            </button>
          </form>
        </div>
      )}
    </div>
  );
};
