/* DNSmith Ingress UI.
 *
 * Four views, one state object, no framework. The whole interface is small
 * enough that a router and a re-render function do the job, and staying
 * build-free means the add-on image has no node toolchain in it and the page
 * works on a Home Assistant with no internet access.
 */

import { api, ApiError } from './api.js';
import { buildForm, el, monogram } from './forms.js';

const view = document.getElementById('view');
const toastBox = document.getElementById('toast');

const state = {
  view: 'dashboard',
  status: null,
  providers: null,
  query: '',
  category: null,
  provider: null,
  form: null,
  record: null,
  busy: false,
};

let toastTimer = null;

function toast(message, bad = false) {
  toastBox.textContent = message;
  toastBox.classList.toggle('is-bad', bad);
  toastBox.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toastBox.hidden = true; }, bad ? 7000 : 3500);
}

function show(node) {
  view.replaceChildren(node);
}

function loading(text = 'Wird geladen…') {
  show(el('div', { class: 'loading' }, [
    el('span', { class: 'spinner', 'aria-hidden': 'true' }),
    document.createTextNode(text),
  ]));
}

function describeError(error) {
  if (error instanceof ApiError) return error.message;
  return String(error && error.message ? error.message : error);
}

/* --- dashboard --------------------------------------------------------- */

function addressCard(status) {
  const ip = status.public_ip || {};

  const box = (label, value, missing) => el('div', { class: 'ip-box' }, [
    el('div', { class: 'ip-label', text: label }),
    value
      ? el('div', { class: 'ip-value mono', text: value })
      : el('div', { class: 'ip-value is-missing', text: missing }),
  ]);

  const card = el('div', { class: 'card' }, [
    el('div', { class: 'ip-grid' }, [
      box('Öffentliche IPv4', ip.ipv4, 'nicht gefunden'),
      box('Öffentliche IPv6', ip.ipv6, 'nicht gefunden'),
    ]),
    el('div', { class: 'stat-row' }, [
      el('div', { class: 'stat' }, [
        el('b', { text: String(status.records_total) }),
        el('span', { text: status.records_total === 1 ? 'Eintrag' : 'Einträge' }),
      ]),
      el('div', { class: `stat${status.records_failed ? ' is-bad' : ''}` }, [
        el('b', { text: String(status.records_failed) }),
        el('span', { text: 'fehlerhaft' }),
      ]),
    ]),
  ]);

  for (const notice of ip.notices || []) {
    card.append(el('div', { class: 'notice', text: notice.message }));
  }
  if (ip.error) {
    card.append(el('div', { class: 'notice is-error', text: ip.error.message }));
  }

  return card;
}

function dotClass(state_) {
  if (state_ === 'success' || state_ === 'up_to_date') return 'dot is-ok';
  if (state_ === 'fail') return 'dot is-bad';
  if (state_ === 'updating') return 'dot is-busy';
  return 'dot';
}

const STATE_TEXT = {
  success: 'aktualisiert',
  up_to_date: 'aktuell',
  updating: 'wird aktualisiert',
  fail: 'fehlgeschlagen',
  unset: 'noch kein Update',
  disabled: 'deaktiviert',
};

function relativeTime(iso) {
  if (!iso) return null;
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return null;

  const seconds = Math.round((Date.now() - then) / 1000);
  if (seconds < 60) return 'gerade eben';
  if (seconds < 3600) return `vor ${Math.floor(seconds / 60)} min`;
  if (seconds < 86400) return `vor ${Math.floor(seconds / 3600)} h`;
  return `vor ${Math.floor(seconds / 86400)} Tagen`;
}

function errorBox(error) {
  const box = el('div', { class: 'error-box' }, [
    el('div', { text: error.message }),
  ]);

  if (error.checks && error.checks.length) {
    box.append(el('ul', {}, error.checks.map((check) => el('li', { text: check }))));
  }

  if (error.technical || error.detail) {
    const details = el('details', { class: 'tech' }, [
      el('summary', { text: 'Technische Details' }),
      el('pre', { text: [error.technical, error.detail].filter(Boolean).join('\n') }),
    ]);
    box.append(details);
  }

  return box;
}

function recordRow(record) {
  const status = record.status || { state: 'unset' };
  const bits = [record.provider_name, ipVersionLabel(record.ip_version)];

  const when = relativeTime(status.last_success || status.last_attempt);
  bits.push(STATE_TEXT[status.state] || status.state);
  if (when) bits.push(when);

  const main = el('div', { class: 'record-main' }, [
    el('div', { class: 'record-name', text: record.display_name }),
    el('div', { class: 'record-meta', text: bits.join(' · ') }),
  ]);

  if (record.label && record.label !== record.fqdn) {
    main.querySelector('.record-meta').textContent = `${record.fqdn} · ${bits.join(' · ')}`;
  }

  if (status.error) main.append(errorBox(status.error));

  return el('div', { class: 'record' }, [
    el('span', { class: dotClass(status.state), title: STATE_TEXT[status.state] || '' }),
    main,
    el('div', { class: 'record-actions' }, [
      el('button', {
        class: 'btn is-small',
        text: 'Aktualisieren',
        disabled: state.busy || !record.enabled,
        onclick: () => forceUpdate(record.id),
      }),
      el('button', {
        class: 'btn is-small',
        text: 'Bearbeiten',
        onclick: () => openRecord(record.id),
      }),
    ]),
  ]);
}

function ipVersionLabel(value) {
  return {
    ipv4: 'IPv4',
    ipv6: 'IPv6',
    dual_stack: 'IPv4 + IPv6',
    ipv4_or_ipv6: 'IPv4 oder IPv6',
  }[value] || value;
}

function renderDashboard() {
  const status = state.status;
  const node = el('div', {});

  // First, above everything, and not dismissible: an empty list looks exactly
  // like a fresh installation, so without this the worst case reads as the
  // most ordinary one.
  if (status.config_error) {
    node.append(el('div', { class: 'card is-alarm' }, [
      el('h3', { text: 'Die gespeicherte Konfiguration konnte nicht gelesen werden' }),
      el('p', { text: status.config_error }),
      el('p', { class: 'small muted', text:
        'Es wird nichts gespeichert und nichts aktualisiert, solange das so ist — '
        + 'die Datei bleibt unangetastet. Nach dem Reparieren die App neu starten.' }),
    ]));
  }

  node.append(addressCard(status));

  node.append(el('div', { class: 'section-head' }, [
    el('h2', { text: 'Einträge' }),
    el('div', { class: 'btn-row', style: 'margin:0' }, [
      status.records_total
        ? el('button', {
            class: 'btn is-small',
            text: 'Alle aktualisieren',
            disabled: state.busy,
            onclick: forceUpdateAll,
          })
        : null,
      el('button', {
        class: 'btn is-primary is-small',
        text: '+ Anbieter hinzufügen',
        onclick: openPicker,
      }),
    ]),
  ]));

  if (!status.records.length) {
    node.append(el('div', { class: 'card' }, [
      el('div', { class: 'empty' }, [
        el('h3', { text: 'Noch kein Eintrag' }),
        el('p', {
          text: 'Wähle deinen DDNS-Anbieter aus, trage die Zugangsdaten ein — fertig.',
        }),
        el('button', {
          class: 'btn is-primary',
          text: 'Anbieter auswählen',
          onclick: openPicker,
        }),
      ]),
    ]));
  } else {
    const card = el('div', { class: 'card' });
    for (const record of status.records) card.append(recordRow(record));
    node.append(card);
  }

  show(node);
}

async function loadDashboard() {
  loading();
  try {
    state.status = await api.status();
    state.view = 'dashboard';
    markTab('dashboard');
    renderDashboard();
  } catch (error) {
    show(el('div', { class: 'card' }, [
      el('div', { class: 'empty' }, [
        el('h3', { text: 'Die Übersicht konnte nicht geladen werden' }),
        el('p', { text: describeError(error) }),
        el('button', { class: 'btn', text: 'Erneut versuchen', onclick: loadDashboard }),
      ]),
    ]));
  }
}

/* --- provider picker --------------------------------------------------- */

const CATEGORY_LABELS = {
  free_ddns: 'Kostenlos',
  commercial_ddns: 'Kommerziell',
  dns_provider: 'DNS-Anbieter',
  cloud_dns: 'Cloud-DNS',
  registrar: 'Registrar',
  german: 'Deutschsprachig',
  ipv6_focused: 'IPv6',
  dyndns2_compatible: 'DynDNS2',
  generic: 'Generisch',
};

async function openPicker() {
  state.view = 'picker';
  loading();
  try {
    const data = await api.providers(state.query, state.category);
    state.providers = data;
    renderPicker();
  } catch (error) {
    toast(describeError(error), true);
  }
}

function renderPicker() {
  const data = state.providers;

  const search = el('input', {
    class: 'search',
    type: 'search',
    placeholder: `Unter ${data.total} Anbietern suchen…`,
    value: state.query,
    'aria-label': 'Anbieter suchen',
  });

  let debounce = null;
  search.addEventListener('input', () => {
    state.query = search.value;
    clearTimeout(debounce);
    debounce = setTimeout(async () => {
      state.providers = await api.providers(state.query, state.category);
      renderPicker();
      // Redrawing steals focus; put it back where the user was typing.
      const field = view.querySelector('.search');
      if (field) {
        field.focus();
        field.setSelectionRange(field.value.length, field.value.length);
      }
    }, 180);
  });

  const chips = el('div', { class: 'chips' }, [
    el('button', {
      class: `chip${state.category ? '' : ' is-active'}`,
      text: 'Alle',
      onclick: () => { state.category = null; openPicker(); },
    }),
  ]);

  for (const [name, count] of Object.entries(data.categories)) {
    chips.append(el('button', {
      class: `chip${state.category === name ? ' is-active' : ''}`,
      text: `${CATEGORY_LABELS[name] || name} (${count})`,
      onclick: () => { state.category = name; openPicker(); },
    }));
  }

  const popular = data.providers.filter((provider) => provider.popular);
  const rest = data.providers.filter((provider) => !provider.popular);

  const node = el('div', {}, [
    el('button', { class: 'back', text: '← Zurück zur Übersicht', onclick: loadDashboard }),
    el('div', { class: 'card' }, [search, chips]),
  ]);

  if (popular.length) {
    node.append(el('div', { class: 'section-head' }, [el('h2', { text: 'Häufig genutzt' })]));
    node.append(providerGrid(popular));
  }

  if (rest.length) {
    node.append(el('div', { class: 'section-head' }, [
      el('h2', { text: popular.length ? 'Alle weiteren Anbieter' : 'Anbieter' }),
    ]));
    node.append(providerGrid(rest));
  }

  if (!data.providers.length) {
    node.append(el('div', { class: 'card' }, [
      el('div', { class: 'empty' }, [
        el('h3', { text: 'Kein Treffer' }),
        el('p', {
          text: 'Steht dein Anbieter nicht in der Liste, funktioniert oft '
              + '„Generisches DynDNS2“ — oder der eigene HTTP-Provider.',
        }),
      ]),
    ]));
  }

  show(node);
}

function providerGrid(providers) {
  return el('div', { class: 'provider-grid' },
    providers.map((provider) => el('button', {
      // Providers without an updater stay in the list and stay clickable.
      // Hiding them would answer "is my provider supported?" with silence,
      // and the form explains the situation better than an absence can.
      class: provider.ported === false ? 'provider provider-unported' : 'provider',
      type: 'button',
      onclick: () => openForm(provider.id),
    }, [
      monogram(provider),
      el('div', { class: 'provider-text' }, [
        el('div', { class: 'provider-name' }, [
          document.createTextNode(provider.name),
          provider.ported === false
            ? el('span', { class: 'badge', text: 'noch nicht verfügbar' })
            : null,
          provider.capabilities && !provider.capabilities.ipv6
            ? el('span', { class: 'badge', text: 'nur IPv4' })
            : null,
        ]),
        provider.description
          ? el('div', { class: 'provider-desc', text: provider.description })
          : null,
      ]),
    ])));
}

/* --- provider form ----------------------------------------------------- */

async function openForm(providerId, record = null) {
  loading();
  try {
    const form = await api.providerForm(providerId);
    state.view = 'form';
    state.provider = providerId;
    state.form = form;
    state.record = record;
    renderForm();
  } catch (error) {
    toast(describeError(error), true);
    loadDashboard();
  }
}

async function openRecord(recordId) {
  loading();
  try {
    const record = await api.record(recordId);
    await openForm(record.provider_id, record);
  } catch (error) {
    toast(describeError(error), true);
    loadDashboard();
  }
}

function renderForm() {
  const form = state.form;
  const record = state.record;
  const editing = Boolean(record);

  const domain = el('input', {
    type: 'text',
    id: 'f-domain',
    placeholder: 'example.com',
    value: record ? record.domain : '',
    disabled: editing,
    spellcheck: 'false',
  });

  const owner = el('input', {
    type: 'text',
    id: 'f-owner',
    placeholder: '@ für die Domain selbst',
    value: record ? record.owner : '@',
    disabled: editing,
    spellcheck: 'false',
  });

  const ipVersion = el('select', { id: 'f-ipversion', disabled: editing });
  for (const option of form.ip_versions) {
    ipVersion.append(el('option', { value: option.value, text: option.label }));
  }
  ipVersion.value = record ? record.ip_version : (form.ip_versions[0] || {}).value;

  const label = el('input', {
    type: 'text',
    id: 'f-label',
    placeholder: 'optional, z. B. „Zuhause“',
    value: record ? record.label : '',
  });

  const fields = buildForm(form, { existing: record });

  const identity = el('div', { class: 'card' }, [
    el('h3', { text: 'Adresse' }),
    el('p', { class: 'small muted', text: editing
      ? 'Anbieter, Domain und IP-Version legen die Identität des Eintrags fest und '
        + 'lassen sich nicht ändern. Für eine andere Adresse einen neuen Eintrag anlegen.'
      : 'Der Hostname, den DNSmith aktuell hält.' }),
    el('div', { class: 'field' }, [el('label', { for: 'f-domain', text: 'Domain' }), domain]),
    el('div', { class: 'field' }, [
      el('label', { for: 'f-owner', text: 'Subdomain' }),
      owner,
      el('div', { class: 'help', text: '„@“ bedeutet die Domain selbst, ohne Subdomain.' }),
    ]),
    el('div', { class: 'field' }, [
      el('label', { for: 'f-ipversion', text: 'IP-Version' }),
      ipVersion,
    ]),
    el('div', { class: 'field' }, [el('label', { for: 'f-label', text: 'Bezeichnung' }), label]),
  ]);

  const credentials = el('div', { class: 'card' }, [
    el('h3', { text: 'Zugangsdaten' }),
    form.description ? el('p', { class: 'small muted', text: form.description }) : null,
    fields.element,
  ]);

  if (form.rate_limit && form.rate_limit.note) {
    credentials.append(el('div', { class: 'notice', text: form.rate_limit.note }));
  }
  for (const note of form.notes || []) {
    credentials.append(el('div', { class: 'notice', text: note }));
  }
  // Two different things, so two different labels. For a provider whose
  // update starts with a lookup, the check really asks the provider and
  // proves the credentials. For the rest there is nothing read-only to try,
  // and calling that "Verbindung testen" promises something it cannot do —
  // which is how a test button stops being believed.
  const testButton = el('button', {
    class: 'btn',
    text: form.live_test ? 'Zugangsdaten prüfen' : 'Angaben prüfen',
    title: form.live_test
      ? 'Fragt beim Anbieter nach: stimmen die Zugangsdaten und gibt es die Zone?'
      : 'Prüft die Eingaben. Dieser Anbieter kennt keine Abfrage, die nichts '
        + 'verändert — ob er die Zugangsdaten annimmt, zeigt das erste Update.',
    onclick: () => runTest(fields, collect(), form.live_test),
  });

  const saveButton = el('button', {
    class: 'btn is-primary',
    text: editing ? 'Änderungen speichern' : 'Eintrag anlegen',
    onclick: () => save(fields, collect()),
  });

  function collect() {
    return {
      provider_id: state.provider,
      domain: domain.value.trim(),
      owner: owner.value.trim() || '@',
      ip_version: ipVersion.value,
      label: label.value.trim(),
      auth_variant: fields.authVariant,
      values: fields.values(),
      record_id: record ? record.id : undefined,
    };
  }

  const actions = el('div', { class: 'btn-row' }, [saveButton, testButton]);

  if (editing) {
    actions.append(el('button', {
      class: 'btn is-danger',
      text: 'Löschen',
      onclick: () => remove(record),
    }));
  }

  const node = el('div', {}, [
    el('button', {
      class: 'back',
      text: editing ? '← Zurück zur Übersicht' : '← Anderen Anbieter wählen',
      onclick: editing ? loadDashboard : openPicker,
    }),
    el('div', { class: 'section-head' }, [el('h2', { text: form.name })]),
    identity,
    credentials,
    actions,
  ]);

  show(node);
  if (!editing) domain.focus();
}

async function runTest(fields, payload, liveTest) {
  state.busy = true;
  // Matches the button label/tooltip above: only a lookup-capable provider
  // actually talks to the network here, so only for those is "Verbindung"
  // the honest word for what is happening.
  toast(liveTest ? 'Verbindung wird geprüft…' : 'Angaben werden geprüft…');
  try {
    // "live" asks the server to do the most it safely can. For providers
    // whose update needs a lookup first, that is a real read at the provider;
    // for the rest it falls back to checking the form, and says so. The
    // server decides, because only it knows which kind a provider is.
    const result = await api.test({ ...payload, mode: 'live' });
    fields.showProblems(null);

    if (result.ok) {
      toast(result.message || 'Die Angaben sind vollständig.');
    } else {
      toast(result.error ? result.error.message : 'Der Test ist fehlgeschlagen.', true);
    }
  } catch (error) {
    if (error instanceof ApiError && error.fields) {
      fields.showProblems(error.fields);
      toast('Bitte die markierten Felder prüfen.', true);
    } else {
      toast(describeError(error), true);
    }
  } finally {
    state.busy = false;
  }
}

async function save(fields, payload) {
  state.busy = true;
  try {
    if (payload.record_id) {
      await api.patchRecord(payload.record_id, {
        values: payload.values,
        label: payload.label,
        auth_variant: payload.auth_variant,
      });
      toast('Änderungen gespeichert.');
    } else {
      await api.createRecord(payload);
      toast('Eintrag angelegt — das erste Update läuft bereits.');
    }
  } catch (error) {
    if (error instanceof ApiError && error.fields) {
      fields.showProblems(error.fields);
      toast('Bitte die markierten Felder prüfen.', true);
    } else {
      toast(describeError(error), true);
    }
    return;
  } finally {
    state.busy = false;
  }

  // Rendered only after busy is cleared. Every button reads state.busy at the
  // moment it is built, so drawing the list while the save is still marked as
  // in flight hands the user a row of dead buttons that only come back on the
  // next poll — which looks like the add-on needing a few seconds to think.
  await loadDashboard();
}

async function remove(record) {
  const confirmed = window.confirm(
    `„${record.display_name}“ wirklich löschen?\n\n`
    + 'Der DNS-Eintrag beim Anbieter bleibt bestehen — DNSmith hält ihn nur '
    + 'nicht mehr aktuell.',
  );
  if (!confirmed) return;

  try {
    await api.deleteRecord(record.id);
    toast('Eintrag gelöscht.');
    await loadDashboard();
  } catch (error) {
    toast(describeError(error), true);
  }
}

async function forceUpdate(recordId) {
  state.busy = true;
  toast('Update wird ausgelöst…');
  try {
    const result = await api.updateRecord(recordId);
    toast(result.ok ? 'Update erfolgreich.' : 'Das Update ist fehlgeschlagen.', !result.ok);
  } catch (error) {
    toast(describeError(error), true);
  } finally {
    // Cleared BEFORE redrawing, for the reason spelled out in save(): every
    // button reads state.busy as it is built, so a list drawn while this is
    // still true comes back with every button dead until the next poll.
    state.busy = false;
  }
  await loadDashboard();
}

async function forceUpdateAll() {
  state.busy = true;
  toast('Alle Einträge werden aktualisiert…');
  try {
    const result = await api.updateAll();
    toast(result.ok
      ? 'Alle Einträge aktualisiert.'
      : `${result.failed} von ${result.requested} Einträgen fehlgeschlagen.`, !result.ok);
  } catch (error) {
    toast(describeError(error), true);
  } finally {
    state.busy = false;
  }
  await loadDashboard();
}

/* --- settings ---------------------------------------------------------- */

// One address family's source. Which inputs are relevant depends on the mode,
// so the irrelevant ones are hidden rather than disabled: a field that cannot
// affect anything is noise, and noise in a settings page gets filled in.
function ipSourceFields(family, source) {
  const label = family === 'v4' ? 'IPv4' : 'IPv6';
  const current = source || { mode: 'auto' };

  const mode = el('select', { id: `s-src-${family}` });
  for (const [value, text] of [
    ['auto', 'Automatisch über das Internet ermitteln'],
    ['ha_entity', 'Aus einer Home-Assistant-Entität lesen'],
    ['static', 'Feste Adresse verwenden'],
    ['disabled', `Kein ${label} verwenden`],
  ]) {
    const option = el('option', { value, text });
    if (current.mode === value) option.selected = true;
    mode.append(option);
  }

  const entity = el('input', {
    type: 'text', id: `s-entity-${family}`, value: current.entity_id || '',
    placeholder: family === 'v6' ? 'sensor.fritzbox_externe_ipv6' : 'sensor.fritzbox_externe_ip',
  });
  const value = el('input', {
    type: 'text', id: `s-value-${family}`, value: current.value || '',
    placeholder: family === 'v6' ? '2001:db8::1' : '203.0.113.7',
  });

  const entityField = el('div', { class: 'field' }, [
    el('label', { for: entity.id, text: 'Entität' }),
    entity,
    el('div', { class: 'help', text:
      'Die Entität muss als Zustand die Adresse selbst enthalten. '
      + 'Ist sie „nicht verfügbar“, lässt DNSmith den Eintrag unangetastet, '
      + 'statt ihn auf etwas Falsches zu setzen.' }),
  ]);
  const valueField = el('div', { class: 'field' }, [
    el('label', { for: value.id, text: 'Adresse' }),
    value,
  ]);

  function sync() {
    entityField.hidden = mode.value !== 'ha_entity';
    valueField.hidden = mode.value !== 'static';
  }
  mode.addEventListener('change', sync);
  sync();

  const node = el('div', { class: 'field-group' }, [
    el('div', { class: 'field' }, [
      el('label', { for: mode.id, text: `${label}-Adresse` }),
      mode,
    ]),
    entityField,
    valueField,
  ]);

  return {
    node,
    value: () => ({
      mode: mode.value,
      entity_id: mode.value === 'ha_entity' ? entity.value.trim() : null,
      value: mode.value === 'static' ? value.value.trim() : null,
    }),
  };
}

async function loadSettings() {
  state.view = 'settings';
  markTab('settings');
  loading();

  try {
    const settings = await api.settings();

    const poll = el('input', { type: 'text', id: 's-poll', value: settings.poll_interval });
    const cooldown = el('input', { type: 'text', id: 's-cooldown', value: settings.update_cooldown });
    const sourceV4 = ipSourceFields('v4', settings.ip_source_v4);
    const sourceV6 = ipSourceFields('v6', settings.ip_source_v6);

    // One save button for both cards below: a value changed in one and left
    // unsaved must not be silently dropped by saving the other.
    const saveSettings = async () => {
      try {
        await api.saveSettings({
          poll_interval: poll.value.trim(),
          update_cooldown: cooldown.value.trim(),
          ip_source_v4: sourceV4.value(),
          ip_source_v6: sourceV6.value(),
        });
        toast('Einstellungen gespeichert.');
      } catch (error) {
        toast(describeError(error), true);
      }
    };

    const node = el('div', {}, [
      el('div', { class: 'card' }, [
        el('h3', { text: 'Aktualisierung' }),
        el('div', { class: 'field' }, [
          el('label', { for: 's-poll', text: 'Prüfintervall' }),
          poll,
          el('div', { class: 'help', text:
            'Wie oft DNSmith die öffentliche IP prüft. Angabe wie 5m oder 1h. '
            + 'Ein Update beim Anbieter erfolgt nur, wenn sich die Adresse '
            + 'tatsächlich geändert hat.' }),
        ]),
        el('div', { class: 'field' }, [
          el('label', { for: 's-cooldown', text: 'Mindestabstand zwischen Updates' }),
          cooldown,
          el('div', { class: 'help', text:
            'Schützt vor Sperren durch den Anbieter, wenn die IP häufig wechselt.' }),
        ]),
      ]),
      el('div', { class: 'card' }, [
        el('h3', { text: 'Woher die IP-Adressen kommen' }),
        el('p', { class: 'small muted', text:
          'Normalerweise ermittelt DNSmith die Adressen selbst über das Internet. '
          + 'Hat der Container keine IPv6-Route — bei DS-Lite-Anschlüssen der '
          + 'Normalfall —, kennt Home Assistant die externe Adresse trotzdem oft '
          + 'schon, etwa über die Router-Integration.' }),
        sourceV4.node,
        sourceV6.node,
      ]),
      el('div', { class: 'btn-row' }, [
        el('button', { class: 'btn is-primary', text: 'Einstellungen speichern', onclick: saveSettings }),
      ]),
      el('div', { class: 'card' }, [
        el('h3', { text: 'Sicherung' }),
        el('p', { class: 'small muted', text:
          'Der Export enthält standardmäßig keine Zugangsdaten. Eine Sicherung mit '
          + 'Zugangsdaten ist im Klartext lesbar — behandle sie wie ein Passwort.' }),
        el('div', { class: 'btn-row' }, [
          el('a', { class: 'btn', href: api.exportUrl(false), download: 'dnsmith-backup.json',
                    text: 'Ohne Zugangsdaten exportieren' }),
          el('a', { class: 'btn', href: api.exportUrl(true), download: 'dnsmith-backup-full.json',
                    text: 'Mit Zugangsdaten exportieren' }),
        ]),
      ]),
    ]);

    show(node);
  } catch (error) {
    toast(describeError(error), true);
  }
}

/* --- boot -------------------------------------------------------------- */

function markTab(name) {
  for (const tab of document.querySelectorAll('.tab')) {
    tab.classList.toggle('is-active', tab.dataset.view === name);
  }
}

document.getElementById('tabs').addEventListener('click', (event) => {
  const tab = event.target.closest('.tab');
  if (!tab) return;
  if (tab.dataset.view === 'settings') loadSettings();
  else loadDashboard();
});

loadDashboard();

// A slow refresh keeps the dashboard honest without hammering the engine.
// Only while the tab is visible and nothing is mid-flight.
setInterval(() => {
  if (state.view === 'dashboard' && !state.busy && !document.hidden) {
    api.status().then((status) => {
      state.status = status;
      renderDashboard();
    }).catch(() => { /* a transient failure must not replace the view */ });
  }
}, 30000);
