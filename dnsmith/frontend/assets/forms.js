/* Rendering a provider form from its manifest.
 *
 * This file is the whole reason DNSmith exists. It contains no provider
 * names, no special cases, no "if cloudflare then". It reads the form
 * contract the hub sends and draws inputs. Adding a provider is a YAML file;
 * nothing here changes.
 *
 * Three things it has to get right, because each is a place where a naive
 * form would be wrong:
 *
 * - Mutually exclusive credentials. Cloudflare takes an API token OR an
 *   e-mail plus global key OR a service key. Showing all six at once is what
 *   the existing add-on does and what makes it hard to use.
 * - Dependent fields. A field with a `when` condition only exists once the
 *   field it depends on has the right value.
 * - Stored secrets. A secret input cannot be prefilled, so on an edit it
 *   shows as "set" and an empty submission means "keep it".
 */

export function el(tag, attributes = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attributes)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else if (value === true) node.setAttribute(key, '');
    else node.setAttribute(key, value);
  }
  for (const child of [].concat(children)) {
    if (child) node.append(child);
  }
  return node;
}

/** A stable colour per provider, so the monogram is recognisable. */
export function monogramColour(id) {
  let hash = 0;
  for (let index = 0; index < id.length; index += 1) {
    hash = (hash * 31 + id.charCodeAt(index)) >>> 0;
  }
  // Fixed saturation and lightness keep contrast against white text usable
  // for every hue.
  return `hsl(${hash % 360}deg 48% 42%)`;
}

/** Initials for a provider with no logo.
 *
 * Two letters, not one. With one letter per word, every single-word name
 * collapses to its first character, and this catalogue has Dyn, Dynu, DynV6,
 * DuckDNS, DNSPod and DonDominio in it — six tiles reading "D" in six
 * different colours is not an icon, it is a colour-matching exercise.
 */
export function initials(provider) {
  const cleaned = (provider.name || provider.id).replace(/[^A-Za-z0-9 ]/g, ' ').trim();
  const words = cleaned.split(/\s+/).filter(Boolean);
  if (!words.length) return '?';
  if (words.length === 1) return words[0].slice(0, 2).replace(/^./, (c) => c.toUpperCase());
  return words.slice(0, 2).map((word) => word[0].toUpperCase()).join('');
}

/** The tile in front of a provider name: its icon, or its initials.
 *
 * The icon is the provider's own favicon, fetched by tools/fetch_logos.py.
 * Those are full-colour raster images, so they are drawn as an <img> on a
 * neutral tile rather than recoloured — a masked favicon would throw away
 * the very thing that makes it recognisable.
 *
 * The URL is resolved against the document base, the same rule api.js
 * follows: under Ingress the add-on lives below a generated prefix, and a
 * leading slash would leave the add-on.
 *
 * onerror matters. Not every provider has an icon, and the hub lists only
 * the files it actually found - but a stale page against a rebuilt image can
 * still ask for one that is gone. When that happens the tile falls back to
 * initials instead of showing a broken image.
 */
export function monogram(provider) {
  if (provider.logo) {
    const href = new URL(String(provider.logo).replace(/^\/+/, ''), new URL('./', document.baseURI));
    const tile = el('span', { class: 'monogram monogram-logo' });
    const image = el('img', { src: href.toString(), alt: '', loading: 'lazy' });
    image.addEventListener('error', () => {
      tile.classList.remove('monogram-logo');
      tile.style.background = provider.brand_color || monogramColour(provider.id);
      tile.textContent = initials(provider);
    });
    tile.append(image);
    return tile;
  }

  return el('span', {
    class: 'monogram',
    text: initials(provider),
    'aria-hidden': 'true',
    style: `background:${provider.brand_color || monogramColour(provider.id)}`,
  });
}

/**
 * Build the fields of a provider form.
 *
 * Returns an object with `element` and `values()`. `values()` omits secret
 * inputs that were left blank, which is what makes "leave it alone" the
 * default on an edit.
 */
export function buildForm(form, { existing = null, problems = {} } = {}) {
  const container = el('div');
  const inputs = new Map();
  const secretIds = new Set(form.fields.filter((field) => field.secret).map((f) => f.id));

  let activeVariant = form.auth ? form.auth.default : null;

  const variantFields = new Map();
  if (form.auth) {
    for (const variant of form.auth.variants) {
      for (const name of variant.fields) variantFields.set(name, variant.id);
    }
  }

  // A record only ever stores the fields of the variant it was created
  // with — the other variant's fields are simply absent. That makes any
  // field present on `existing` proof of which variant is actually in use,
  // which is why this can be a lookup rather than something the server has
  // to remember separately.
  if (form.auth && existing) {
    const present = [
      ...(existing.fields ? Object.keys(existing.fields) : []),
      ...(existing.secrets
        ? Object.keys(existing.secrets).filter((id) => existing.secrets[id] && existing.secrets[id].set)
        : []),
    ];
    const usedVariant = present.map((id) => variantFields.get(id)).find(Boolean);
    if (usedVariant) activeVariant = usedVariant;
  }

  // --- authentication chooser -------------------------------------------
  let variantBox = null;
  if (form.auth) {
    variantBox = el('div', { class: 'field' }, [
      el('label', { text: 'Anmeldeverfahren' }),
    ]);

    for (const variant of form.auth.variants) {
      const radio = el('input', {
        type: 'radio',
        name: 'auth-variant',
        value: variant.id,
        checked: variant.id === activeVariant,
      });

      radio.addEventListener('change', () => {
        activeVariant = variant.id;
        refresh();
      });

      const label = el('div', {}, [
        el('div', {}, [
          document.createTextNode(variant.label),
          variant.recommended ? el('span', { class: 'badge', text: 'empfohlen' }) : null,
          variant.deprecated ? el('span', { class: 'badge', text: 'veraltet' }) : null,
        ]),
        variant.hint ? el('div', { class: 'variant-hint', text: variant.hint }) : null,
      ]);

      const row = el('label', { class: 'variant' }, [radio, label]);
      row.dataset.variant = variant.id;
      variantBox.append(row);
    }

    container.append(variantBox);
  }

  // --- fields ------------------------------------------------------------
  for (const field of form.fields) {
    const wrapper = el('div', { class: 'field' });
    wrapper.dataset.field = field.id;

    const stored = existing && existing.secrets && existing.secrets[field.id];
    const isSet = Boolean(stored && stored.set);
    const current = existing && existing.fields ? existing.fields[field.id] : undefined;

    let input;

    if (field.type === 'boolean') {
      input = el('input', { type: 'checkbox', id: `f-${field.id}` });
      input.checked = current !== undefined ? Boolean(current) : Boolean(field.default);
      wrapper.className = 'field field-check';
      wrapper.append(input, el('div', {}, [
        el('label', { for: `f-${field.id}`, text: field.label }),
        field.help ? el('div', { class: 'help', text: field.help }) : null,
      ]));
    } else {
      const labelNode = el('label', { for: `f-${field.id}` }, [
        document.createTextNode(field.label),
        field.required ? el('span', { class: 'req', text: '*', title: 'erforderlich' }) : null,
      ]);
      wrapper.append(labelNode);

      if (field.type === 'select') {
        input = el('select', { id: `f-${field.id}` });
        for (const option of field.options || []) {
          input.append(el('option', { value: option.value, text: option.label }));
        }
        input.value = current !== undefined ? current : (field.default ?? '');
      } else if (field.type === 'multiline_secret') {
        input = el('textarea', {
          id: `f-${field.id}`,
          placeholder: isSet ? 'Gespeichert — leer lassen, um es zu behalten' : '',
        });
      } else {
        input = el('input', {
          id: `f-${field.id}`,
          type: inputType(field),
          class: field.ui && field.ui.monospace ? 'mono' : null,
          placeholder: isSet ? 'Gespeichert — leer lassen, um es zu behalten' : (field.placeholder || ''),
          autocomplete: field.secret ? 'new-password' : 'off',
          spellcheck: 'false',
        });
        if (!field.secret && current !== undefined && current !== null) {
          input.value = String(current);
        } else if (!field.secret && field.default !== undefined && field.default !== null
                   && existing === null) {
          input.value = String(field.default);
        }
      }

      wrapper.append(input);

      if (field.secret && isSet) {
        wrapper.append(el('div', { class: 'secret-set' }, [
          el('span', { text: '••••••••' }),
          el('span', { text: 'gespeichert' }),
        ]));
      }

      if (field.help) wrapper.append(el('div', { class: 'help', text: field.help }));
    }

    if (problems[field.id]) {
      wrapper.classList.add('has-problem');
      wrapper.append(el('div', { class: 'problem', text: problems[field.id] }));
    }

    inputs.set(field.id, { field, input, wrapper });
    container.append(wrapper);
  }

  // --- visibility --------------------------------------------------------
  function currentValues() {
    const values = {};
    for (const [id, entry] of inputs) {
      if (!isVisible(entry.field)) continue;
      values[id] = readValue(entry);
    }
    return values;
  }

  function isVisible(field) {
    // A field belonging to an authentication variant exists only while that
    // variant is chosen.
    const owner = variantFields.get(field.id);
    if (owner && owner !== activeVariant) return false;

    if (field.when) {
      const source = inputs.get(field.when.field);
      if (!source) return false;
      return readValue(source) === field.when.equals;
    }
    return true;
  }

  function refresh() {
    for (const [, entry] of inputs) {
      entry.wrapper.hidden = !isVisible(entry.field);
    }
    if (variantBox) {
      for (const row of variantBox.querySelectorAll('.variant')) {
        row.classList.toggle('is-active', row.dataset.variant === activeVariant);
      }
    }
  }

  // A `when` condition can point at any field, so any change may reveal or
  // hide another.
  for (const [, entry] of inputs) {
    entry.input.addEventListener('change', refresh);
    entry.input.addEventListener('input', refresh);
  }
  refresh();

  return {
    element: container,
    get authVariant() {
      return activeVariant;
    },
    values() {
      const values = {};
      for (const [id, entry] of inputs) {
        if (!isVisible(entry.field)) continue;
        const value = readValue(entry);
        // A blank secret means "keep what is stored"; sending "" would
        // delete it.
        if (secretIds.has(id) && value === '') continue;
        values[id] = value;
      }
      return values;
    },
    focusFirst() {
      for (const [, entry] of inputs) {
        if (!entry.wrapper.hidden) {
          entry.input.focus();
          return;
        }
      }
    },
    showProblems(fields) {
      for (const [id, entry] of inputs) {
        entry.wrapper.classList.remove('has-problem');
        const existingProblem = entry.wrapper.querySelector('.problem');
        if (existingProblem) existingProblem.remove();

        if (fields && fields[id]) {
          entry.wrapper.classList.add('has-problem');
          entry.wrapper.append(el('div', { class: 'problem', text: fields[id] }));
        }
      }
    },
  };
}

function inputType(field) {
  switch (field.type) {
    case 'secret': return 'password';
    case 'email': return 'email';
    case 'integer': return 'number';
    case 'url': return 'url';
    default: return 'text';
  }
}

function readValue(entry) {
  const { field, input } = entry;
  if (field.type === 'boolean') return input.checked;
  if (field.type === 'integer') {
    return input.value === '' ? '' : Number(input.value);
  }
  return input.value.trim();
}
