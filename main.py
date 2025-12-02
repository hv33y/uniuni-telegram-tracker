export default {
  async fetch(request, env) {
    if (request.method === "POST") {
      try {
        const payload = await request.json();

        if (payload.callback_query) {
          const data = payload.callback_query.data;
          const chatId = payload.callback_query.message.chat.id;
          const messageId = payload.callback_query.message.message_id;
          const callbackId = payload.callback_query.id;

          // Acknowledge the click immediately
          await answerCallback(callbackId, "", env);

          if (data === "refresh") {
            await editMessage(chatId, messageId, "🔄 *Requesting update from server...*\nThis takes about 30 seconds for the GitHub Action to start.", null, env);
            await triggerGitHub(env, "check", null, true); // true = force report
          } 
          else if (data === "manage_menu") {
            await showManageMenu(chatId, messageId, env);
          }
          else if (data === "view_all") {
            await showTrackingList(chatId, messageId, env);
          }
          else if (data === "add_item") {
            await promptForNumber(chatId, env);
          }
          else if (data === "delete_menu") {
            await showDeleteMenu(chatId, messageId, env);
          }
          else if (data.startsWith("del_")) {
            const numberToDelete = data.split("_")[1];
            await editMessage(chatId, messageId, `🗑️ *Deleting ${numberToDelete}...*`, null, env);
            await triggerGitHub(env, "delete", numberToDelete);
          }
          else if (data === "main_menu") {
            await showMainMenu(chatId, messageId, env);
          }
          
          return new Response("OK");
        }

        // Handle Text Messages (For Adding Numbers & /start)
        if (payload.message && payload.message.text) {
          const text = payload.message.text.trim();
          const chatId = payload.message.chat.id;
          const replyTo = payload.message.reply_to_message;

          // If this is a reply to our "Send me the number" prompt
          if (replyTo && replyTo.text === "Please reply with the tracking number:") {
             // Trim the tracking number and trigger the 'add' action
             await sendMessage(chatId, `⏳ *Adding ${text} to the list...*\nI'll notify you when it's saved.`, env);
             await triggerGitHub(env, "add", text);
             return new Response("OK");
          }

          // Handle /start command
          if (text.toLowerCase().startsWith("/start")) {
             await sendMainMenu(chatId, env);
          }
        }

      } catch (e) {
        console.error("Worker Catch Block Error:", e);
      }
    }
    return new Response("OK");
  }
};

// --- UI Functions ---

async function sendMainMenu(chatId, env) {
  const text = "📦 *Package Tracker Control*\n\nWhat would you like to do?";
  const buttons = {
    inline_keyboard: [
      [{ text: "🔄 Refresh Status (Force Check)", callback_data: "refresh" }],
      [{ text: "📝 Manage Tracking Numbers", callback_data: "manage_menu" }]
    ]
  };
  await sendMessage(chatId, text, env, buttons);
}

async function showMainMenu(chatId, messageId, env) {
    const text = "📦 *Package Tracker Control*\n\nWhat would you like to do?";
    const buttons = {
      inline_keyboard: [
        [{ text: "🔄 Refresh Status (Force Check)", callback_data: "refresh" }],
        [{ text: "📝 Manage Tracking Numbers", callback_data: "manage_menu" }]
      ]
    };
    await editMessage(chatId, messageId, text, buttons, env);
}

async function showManageMenu(chatId, messageId, env) {
  const packages = await fetchPackagesFromGitHub(env);
  const text = `📝 *Management Menu*\n\nCurrently tracking ${packages.length} packages.`;
  
  // Conditionally disable delete button if list is empty
  const deleteButton = packages.length > 0
    ? { text: "➖ Delete Number", callback_data: "delete_menu" }
    : { text: "➖ Delete Number (List Empty)", callback_data: "manage_menu" };

  const buttons = {
    inline_keyboard: [
      [{ text: "👀 View All Packages", callback_data: "view_all" }],
      [{ text: "➕ Add New Number", callback_data: "add_item" }, deleteButton],
      [{ text: "🔙 Back to Main", callback_data: "main_menu" }]
    ]
  };
  await editMessage(chatId, messageId, text, buttons, env);
}

async function showTrackingList(chatId, messageId, env) {
    const packages = await fetchPackagesFromGitHub(env);
    
    let text = "*📦 Active Tracking Numbers:*\n\n";
    if (packages.length === 0) {
        text += "_No packages found. Use 'Add New Number' to start tracking._";
    } else {
        packages.forEach((p, index) => {
            const num = p.number.toUpperCase();
            let carrier = 'UniUni'; // Default to UniUni
            
            // Only label as FedEx if it looks strictly like FedEx (Numeric)
            if (/^\d+$/.test(num) && (num.length === 12 || num.length === 15 || num.length === 20 || num.length === 22)) {
                carrier = 'FedEx';
            }
            
            text += `*${index + 1}.* (${carrier}) \`${p.number}\`\nStatus: _${p.last_status || 'New'}_ \n\n`;
        });
    }

    const buttons = {
        inline_keyboard: [[{ text: "🔙 Back to Management", callback_data: "manage_menu" }]]
    };
    await editMessage(chatId, messageId, text, buttons, env);
}

async function promptForNumber(chatId, env) {
    // Sends a message that forces the user's client to reply
    const url = `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`;
    const payload = {
        chat_id: chatId,
        text: "Please reply with the tracking number:",
        reply_markup: { force_reply: true, selective: true }
    };
    await fetch(url, { method: 'POST', body: JSON.stringify(payload), headers: { 'Content-Type': 'application/json' }});
}

async function showDeleteMenu(chatId, messageId, env) {
    const packages = await fetchPackagesFromGitHub(env);
    
    if (packages.length === 0) {
        await editMessage(chatId, messageId, "⚠️ *No packages to delete.*", {
            inline_keyboard: [[{ text: "🔙 Back", callback_data: "manage_menu" }]]
        }, env);
        return;
    }

    let buttons = [];
    // Create buttons for each tracking number
    packages.forEach(p => {
        buttons.push([{ text: `❌ ${p.number}`, callback_data: `del_${p.number}` }]);
    });
    buttons.push([{ text: "🔙 Back to Management", callback_data: "manage_menu" }]);

    await editMessage(chatId, messageId, "Select a number to delete:", { inline_keyboard: buttons }, env);
}

// --- Helper API Functions ---

async function fetchPackagesFromGitHub(env) {
    const url = `https://api.github.com/repos/${env.GITHUB_USER}/${env.GITHUB_REPO}/contents/tracking.json`;
    
    // The GITHUB_PAT is required here to read the private tracking.json file
    const response = await fetch(url, {
        headers: {
            "Authorization": `Bearer ${env.GITHUB_PAT}`,
            "Accept": "application/vnd.github.v3.raw", 
            "User-Agent": "TelegramBot"
        }
    });

    if (!response.ok) return [];
    try {
        const data = await response.json();
        return data.packages || [];
    } catch (e) {
        // Handles case where tracking.json is malformed or empty
        return [];
    }
}

async function triggerGitHub(env, mode, number = null, force = false) {
    // Triggers the repository_dispatch event in main.yml
    const url = `https://api.github.com/repos/${env.GITHUB_USER}/${env.GITHUB_REPO}/dispatches`;
    await fetch(url, {
        method: "POST",
        headers: {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": `Bearer ${env.GITHUB_PAT}`,
            "User-Agent": "TelegramBot"
        },
        body: JSON.stringify({
            event_type: "bot_command", // Matches the type in main.yml
            client_payload: {
                mode: mode,
                number: number,
                force: force ? "true" : "false"
            }
        })
    });
}

async function sendMessage(chatId, text, env, replyMarkup = null) {
    const url = `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`;
    const payload = { chat_id: chatId, text: text, parse_mode: "Markdown" };
    if (replyMarkup) payload.reply_markup = replyMarkup;
    await fetch(url, { method: 'POST', body: JSON.stringify(payload), headers: { 'Content-Type': 'application/json' }});
}

async function editMessage(chatId, messageId, text, replyMarkup, env) {
    const url = `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/editMessageText`;
    const payload = { chat_id: chatId, message_id: messageId, text: text, parse_mode: "Markdown" };
    if (replyMarkup) payload.reply_markup = replyMarkup;
    await fetch(url, { method: 'POST', body: JSON.stringify(payload), headers: { 'Content-Type': 'application/json' }});
}

async function answerCallback(callbackId, text, env) {
  await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/answerCallbackQuery`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ callback_query_id: callbackId, text: text })
  });
}
