/*
 * lsa-nl80211 - deliberately small generic nl80211 supplement for LSA.
 *
 * Standard iw remains LSA's primary nl80211 tool.  iw has no command for an
 * arbitrary NL80211_CMD_FRAME transmit, however, so this helper supplies only
 * that bounded primitive and its TX-status observation.  It contains no
 * device, chipset, or Android-model policy.
 */
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <errno.h>
#include <linux/genetlink.h>
#include <linux/netlink.h>
#include <linux/nl80211.h>
#include <net/if.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

#define LSA_BUFFER 8192
#define LSA_MAX_FRAME 4096
#define NLA_ALIGNTO 4
#define NLA_ALIGN(len) (((len) + NLA_ALIGNTO - 1) & ~(NLA_ALIGNTO - 1))
#define NLA_HDRLEN ((int) NLA_ALIGN(sizeof(struct nlattr)))
#define NLA_DATA(attr) ((void *) ((char *) (attr) + NLA_HDRLEN))
#define NLA_LEN(attr) ((int) ((attr)->nla_len) - NLA_HDRLEN)
#define NLA_OK(attr, remaining) ((remaining) >= (int) sizeof(struct nlattr) && (attr)->nla_len >= sizeof(struct nlattr) && (attr)->nla_len <= (remaining))
#define NLA_NEXT(attr, remaining) ((remaining) -= NLA_ALIGN((attr)->nla_len), (struct nlattr *) ((char *) (attr) + NLA_ALIGN((attr)->nla_len)))

static unsigned int sequence;

static bool nlmsg_ok_lsa(const struct nlmsghdr *nlh, int remaining) {
    return remaining >= (int) sizeof(*nlh) &&
           nlh->nlmsg_len >= sizeof(*nlh) &&
           nlh->nlmsg_len <= (uint32_t) remaining;
}

static struct nlmsghdr *nlmsg_next_lsa(struct nlmsghdr *nlh, int *remaining) {
    int length = (int) NLMSG_ALIGN(nlh->nlmsg_len);
    *remaining -= length;
    return (struct nlmsghdr *) ((char *) nlh + length);
}

static void die(const char *message) {
    fprintf(stderr, "error=%s errno=%d (%s)\n", message, errno, strerror(errno));
    exit(2);
}

static int nl_open(void) {
    int fd = socket(AF_NETLINK, SOCK_RAW | SOCK_CLOEXEC, NETLINK_GENERIC);
    if (fd < 0) die("netlink_socket");
    struct sockaddr_nl addr = { .nl_family = AF_NETLINK };
    if (bind(fd, (struct sockaddr *) &addr, sizeof(addr)) < 0) die("netlink_bind");
    return fd;
}

static int add_attr(struct nlmsghdr *nlh, size_t limit, uint16_t type, const void *data, size_t length) {
    size_t offset = NLMSG_ALIGN(nlh->nlmsg_len);
    size_t total = NLA_HDRLEN + length;
    if (offset + NLA_ALIGN(total) > limit) return -1;
    struct nlattr *attr = (struct nlattr *) ((char *) nlh + offset);
    attr->nla_type = type;
    attr->nla_len = total;
    if (length) memcpy(NLA_DATA(attr), data, length);
    nlh->nlmsg_len = offset + NLA_ALIGN(total);
    return 0;
}

static int send_message(int fd, struct nlmsghdr *nlh) {
    struct sockaddr_nl kernel = { .nl_family = AF_NETLINK };
    struct iovec iov = { .iov_base = nlh, .iov_len = nlh->nlmsg_len };
    struct msghdr message = { .msg_name = &kernel, .msg_namelen = sizeof(kernel), .msg_iov = &iov, .msg_iovlen = 1 };
    return sendmsg(fd, &message, 0) < 0 ? -1 : 0;
}

static int recv_messages(int fd, char *buffer, size_t size, int timeout_ms) {
    struct timeval timeout = { .tv_sec = timeout_ms / 1000, .tv_usec = (timeout_ms % 1000) * 1000 };
    if (setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) < 0) return -1;
    return recv(fd, buffer, size, 0);
}

static int parse_error(struct nlmsghdr *nlh) {
    if (nlh->nlmsg_type != NLMSG_ERROR) return 1;
    if (nlh->nlmsg_len < NLMSG_LENGTH(sizeof(struct nlmsgerr))) return -EPROTO;
    return ((struct nlmsgerr *) NLMSG_DATA(nlh))->error;
}

static int family_id(int fd, const char *family, int *mlme_group) {
    char buffer[LSA_BUFFER] = {0};
    struct nlmsghdr *nlh = (struct nlmsghdr *) buffer;
    struct genlmsghdr *genl;
    nlh->nlmsg_len = NLMSG_LENGTH(sizeof(*genl));
    nlh->nlmsg_type = GENL_ID_CTRL;
    nlh->nlmsg_flags = NLM_F_REQUEST | NLM_F_ACK;
    nlh->nlmsg_seq = ++sequence;
    genl = (struct genlmsghdr *) NLMSG_DATA(nlh);
    genl->cmd = CTRL_CMD_GETFAMILY;
    genl->version = 1;
    if (add_attr(nlh, sizeof(buffer), CTRL_ATTR_FAMILY_NAME, family, strlen(family) + 1)) return -1;
    if (send_message(fd, nlh)) return -1;

    int id = -1;
    for (;;) {
        int received = recv_messages(fd, buffer, sizeof(buffer), 3000);
        if (received < 0) return -1;
        int remaining = received;
        for (nlh = (struct nlmsghdr *) buffer; nlmsg_ok_lsa(nlh, remaining); nlh = nlmsg_next_lsa(nlh, &remaining)) {
            int error = parse_error(nlh);
            if (error <= 0) {
                if (error < 0) { errno = -error; return -1; }
                continue;
            }
            if (nlh->nlmsg_type != GENL_ID_CTRL) continue;
            genl = (struct genlmsghdr *) NLMSG_DATA(nlh);
            int attrs_left = nlh->nlmsg_len - NLMSG_LENGTH(sizeof(*genl));
            struct nlattr *attr = (struct nlattr *) ((char *) genl + GENL_HDRLEN);
            for (; NLA_OK(attr, attrs_left); attr = NLA_NEXT(attr, attrs_left)) {
                if (attr->nla_type == CTRL_ATTR_FAMILY_ID && NLA_LEN(attr) >= (int) sizeof(uint16_t)) {
                    id = *(uint16_t *) NLA_DATA(attr);
                } else if (attr->nla_type == CTRL_ATTR_MCAST_GROUPS && mlme_group) {
                    int groups_left = NLA_LEN(attr);
                    struct nlattr *group = (struct nlattr *) NLA_DATA(attr);
                    for (; NLA_OK(group, groups_left); group = NLA_NEXT(group, groups_left)) {
                        int fields_left = NLA_LEN(group);
                        struct nlattr *field = (struct nlattr *) NLA_DATA(group);
                        const char *name = NULL;
                        int group_id = 0;
                        for (; NLA_OK(field, fields_left); field = NLA_NEXT(field, fields_left)) {
                            if (field->nla_type == CTRL_ATTR_MCAST_GRP_NAME) name = NLA_DATA(field);
                            if (field->nla_type == CTRL_ATTR_MCAST_GRP_ID && NLA_LEN(field) >= (int) sizeof(uint32_t)) group_id = *(uint32_t *) NLA_DATA(field);
                        }
                        if (name && !strcmp(name, "mlme")) *mlme_group = group_id;
                    }
                }
            }
        }
        if (id >= 0) return id;
    }
}

static int decode_hex(const char *text, uint8_t *out, size_t limit) {
    size_t count = 0;
    int high = -1;
    for (; *text; text++) {
        int value;
        if (*text == ':' || *text == '-' || *text == ' ') continue;
        if (*text >= '0' && *text <= '9') value = *text - '0';
        else if (*text >= 'a' && *text <= 'f') value = *text - 'a' + 10;
        else if (*text >= 'A' && *text <= 'F') value = *text - 'A' + 10;
        else return -1;
        if (high < 0) high = value;
        else {
            if (count >= limit) return -1;
            out[count++] = (uint8_t) ((high << 4) | value);
            high = -1;
        }
    }
    return high < 0 ? (int) count : -1;
}

static bool status_event(struct nlmsghdr *nlh, int family, uint64_t cookie, int *acked) {
    if ((int) nlh->nlmsg_type != family || nlh->nlmsg_len < NLMSG_LENGTH(GENL_HDRLEN)) return false;
    struct genlmsghdr *genl = (struct genlmsghdr *) NLMSG_DATA(nlh);
    if (genl->cmd != NL80211_CMD_FRAME_TX_STATUS) return false;
    int attrs_left = nlh->nlmsg_len - NLMSG_LENGTH(sizeof(*genl));
    struct nlattr *attr = (struct nlattr *) ((char *) genl + GENL_HDRLEN);
    uint64_t received_cookie = 0;
    bool has_cookie = false;
    *acked = 0;
    for (; NLA_OK(attr, attrs_left); attr = NLA_NEXT(attr, attrs_left)) {
        if (attr->nla_type == NL80211_ATTR_COOKIE && NLA_LEN(attr) >= (int) sizeof(uint64_t)) { received_cookie = *(uint64_t *) NLA_DATA(attr); has_cookie = true; }
        if (attr->nla_type == NL80211_ATTR_ACK) *acked = 1;
    }
    return has_cookie && received_cookie == cookie;
}

static int frame_tx(const char *ifname, uint32_t frequency, const char *hex, uint32_t wait_ms) {
    uint8_t frame[LSA_MAX_FRAME];
    int frame_len = decode_hex(hex, frame, sizeof(frame));
    if (frame_len < 24) { fprintf(stderr, "error=frame_invalid reason=management_frame_must_be_at_least_24_bytes\n"); return 2; }
    unsigned int ifindex = if_nametoindex(ifname);
    if (!ifindex) { fprintf(stderr, "error=interface_unknown ifname=%s\n", ifname); return 2; }
    int fd = nl_open(), group = 0;
    int family = family_id(fd, "nl80211", &group);
    if (family < 0) die("nl80211_family");
    if (group && setsockopt(fd, SOL_NETLINK, NETLINK_ADD_MEMBERSHIP, &group, sizeof(group)) < 0) die("nl80211_mlme_subscription");

    char buffer[LSA_BUFFER] = {0};
    struct nlmsghdr *nlh = (struct nlmsghdr *) buffer;
    struct genlmsghdr *genl;
    nlh->nlmsg_len = NLMSG_LENGTH(sizeof(*genl));
    nlh->nlmsg_type = family;
    nlh->nlmsg_flags = NLM_F_REQUEST | NLM_F_ACK;
    nlh->nlmsg_seq = ++sequence;
    genl = (struct genlmsghdr *) NLMSG_DATA(nlh);
    genl->cmd = NL80211_CMD_FRAME;
    genl->version = 0;
    if (add_attr(nlh, sizeof(buffer), NL80211_ATTR_IFINDEX, &ifindex, sizeof(ifindex)) ||
        add_attr(nlh, sizeof(buffer), NL80211_ATTR_WIPHY_FREQ, &frequency, sizeof(frequency)) ||
        add_attr(nlh, sizeof(buffer), NL80211_ATTR_DURATION, &wait_ms, sizeof(wait_ms)) ||
        add_attr(nlh, sizeof(buffer), NL80211_ATTR_OFFCHANNEL_TX_OK, NULL, 0) ||
        add_attr(nlh, sizeof(buffer), NL80211_ATTR_FRAME, frame, (size_t) frame_len)) {
        fprintf(stderr, "error=frame_too_large\n"); close(fd); return 2;
    }
    if (send_message(fd, nlh)) die("frame_send");

    uint64_t cookie = 0;
    bool got_cookie = false;
    for (;;) {
        int received = recv_messages(fd, buffer, sizeof(buffer), 3000);
        if (received < 0) die("frame_reply");
        int remaining = received;
        for (nlh = (struct nlmsghdr *) buffer; nlmsg_ok_lsa(nlh, remaining); nlh = nlmsg_next_lsa(nlh, &remaining)) {
            int error = parse_error(nlh);
            if (error <= 0) { if (error < 0) { errno = -error; die("frame_command"); } continue; }
            if ((int) nlh->nlmsg_type != family) continue;
            genl = (struct genlmsghdr *) NLMSG_DATA(nlh);
            int attrs_left = nlh->nlmsg_len - NLMSG_LENGTH(sizeof(*genl));
            struct nlattr *attr = (struct nlattr *) ((char *) genl + GENL_HDRLEN);
            for (; NLA_OK(attr, attrs_left); attr = NLA_NEXT(attr, attrs_left)) {
                if (attr->nla_type == NL80211_ATTR_COOKIE && NLA_LEN(attr) >= (int) sizeof(uint64_t)) { cookie = *(uint64_t *) NLA_DATA(attr); got_cookie = true; }
            }
        }
        if (got_cookie) break;
    }
    printf("command=frame_tx\nstatus=SUBMITTED\ncookie=%llu\n", (unsigned long long) cookie);
    int received = recv_messages(fd, buffer, sizeof(buffer), (int) wait_ms + 1500);
    if (received < 0) { printf("tx_status=UNKNOWN\nreason=timeout_or_unavailable\n"); close(fd); return 0; }
    int remaining = received, acked = 0;
    for (nlh = (struct nlmsghdr *) buffer; nlmsg_ok_lsa(nlh, remaining); nlh = nlmsg_next_lsa(nlh, &remaining)) {
        if (status_event(nlh, family, cookie, &acked)) { printf("tx_status=RECEIVED\nack=%s\n", acked ? "YES" : "NO"); close(fd); return 0; }
    }
    printf("tx_status=UNKNOWN\nreason=no_matching_tx_status\n");
    close(fd);
    return 0;
}

static void usage(const char *program) {
    fprintf(stderr, "usage: %s frame-tx --ifname IFACE --freq MHZ --frame-hex HEX [--wait-ms MS]\n", program);
}

int main(int argc, char **argv) {
    const char *ifname = NULL, *hex = NULL;
    uint32_t frequency = 0, wait_ms = 500;
    if (argc < 2 || strcmp(argv[1], "frame-tx")) { usage(argv[0]); return 2; }
    for (int i = 2; i < argc; i++) {
        if (!strcmp(argv[i], "--ifname") && i + 1 < argc) ifname = argv[++i];
        else if (!strcmp(argv[i], "--freq") && i + 1 < argc) frequency = (uint32_t) strtoul(argv[++i], NULL, 10);
        else if (!strcmp(argv[i], "--frame-hex") && i + 1 < argc) hex = argv[++i];
        else if (!strcmp(argv[i], "--wait-ms") && i + 1 < argc) wait_ms = (uint32_t) strtoul(argv[++i], NULL, 10);
        else { usage(argv[0]); return 2; }
    }
    if (!ifname || !hex || frequency < 2000 || frequency > 7200 || wait_ms > 5000) { usage(argv[0]); return 2; }
    return frame_tx(ifname, frequency, hex, wait_ms);
}
