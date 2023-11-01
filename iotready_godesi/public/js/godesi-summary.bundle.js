import Vue from "vue/dist/vue.js";
import ActivitySummary from './components/summary.vue';

Vue.component('activity-summary', ActivitySummary);

window.constructSummaryView = (context) => new Vue({
  el: '#summary-root',
  data: {
    session_id: context.session_id,
    activity: context.activity,
    crate_summary: context.crate_summary,
    item_summary: context.item_summary,
    crates: context.crates,
  },
  methods: {
    updateVueData: function(key, value) {
      if (key in this.$data) {
        this[key] = value;
      }
    },
    refresh: function() {
      frappe.call({
        method: "bb_fnv_frappe.api_v2.get_session_summary",
        args: {
          session_id: context.session_id,
        },
        callback: (r) => {
          console.log(r);
          if (r.message) {
            for (let k in r.message) {
              this.updateVueData(k, r.message[k]);
            }
          }
        }
      });
    },
    insertCrate: function(crate) {
      // add or replace crate in crates
      this.crates[crate.crate_id] = crate;
    },
    deleteCrate: function(crate_id) {
      // remove crate from crates
      const newCrates = {...this.crates}
      delete newCrates[crate_id];
      this.crates = newCrates;
    },
    update: function(data) {
      if (!data || !typeof data == "string") {
        return;
      }
      const summary = JSON.parse(data);
      if (summary.crate_summary) {
        this.updateCrateSummary(summary.crate_summary);
      }
      if (summary.item_summary) {
        this.updateItemSummary(summary.item_summary)
      }
      if (summary.crate) {
        this.insertCrate(summary.crate);
      }
      if (summary.crates) {
        Object.keys(summary.crates).map((crate_id) => {
          if (summary.crates[crate_id] == null) {
            this.deleteCrate(crate_id);
          } else {
            this.insertCrate(summary.crates[crate_id]);
          }
        });
      }
    },
    updateItemSummary: function(item_summary) {
      this.updateVueData("item_summary", item_summary);
    },
    updateCrateSummary: function(crate_summary) {
      this.updateVueData("crate_summary", crate_summary);
    },
  },
  mounted() {
  },
})

